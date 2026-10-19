"""Offline evaluation and explicit retrieval-config releases. Never calls a model.

Rule checks are mechanical checks only. Semantic scores require human ratings.
The synthetic holdout is evaluation-only, never a source of memory examples.
"""
import argparse
import hashlib
import json
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

BUILTIN = {'max_examples': 3, 'max_context_chars': 4500}
DIMENSIONS = ('relevance', 'naturalness', 'groundedness', 'context_boundaries')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def initialize(db):
    for sql in (
        'CREATE TABLE IF NOT EXISTS eval_versions (id TEXT PRIMARY KEY, config TEXT NOT NULL, sources TEXT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS eval_runs (id TEXT PRIMARY KEY, baseline TEXT NOT NULL, candidate TEXT NOT NULL, report TEXT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS eval_active (singleton INTEGER PRIMARY KEY CHECK(singleton=1), version_id TEXT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS eval_history (sequence INTEGER PRIMARY KEY AUTOINCREMENT, version_id TEXT NOT NULL)',
    ):
        db.execute(sql)


def get_version(db, version_id):
    if version_id == 'builtin':
        return {'id': 'builtin', 'config': dict(BUILTIN), 'sources': []}
    row = db.execute('SELECT config,sources FROM eval_versions WHERE id=?', (version_id,)).fetchone()
    if not row:
        raise ValueError('Version absent or invalidated by source deletion')
    config, sources = json.loads(row[0]), json.loads(row[1])
    if digest({'config': config, 'sources': sources}) != version_id:
        raise ValueError('Version integrity failure')
    for source in sources:
        row = db.execute('SELECT expires_at FROM items WHERE id=?', (source,)).fetchone()
        if not row or row[0] <= datetime.now(timezone.utc).isoformat():
            raise ValueError('Version source deleted or expired')
    return {'id': version_id, 'config': config, 'sources': sources}


def get_active(db):
    initialize(db)
    row = db.execute('SELECT version_id FROM eval_active WHERE singleton=1').fetchone()
    try:
        return get_version(db, row[0] if row else 'builtin')
    except ValueError:
        return get_version(db, 'builtin')


def create_version(db, config, source_ids=()):
    initialize(db)
    if set(config) != set(BUILTIN):
        raise ValueError('Only max_examples and max_context_chars are versioned; no code or prompt injection')
    if type(config['max_examples']) is not int or not 0 <= config['max_examples'] <= 3:
        raise ValueError('max_examples must be an integer from 0 to 3')
    if type(config['max_context_chars']) is not int or not 500 <= config['max_context_chars'] <= 6000:
        raise ValueError('max_context_chars must be an integer from 500 to 6000')
    sources = sorted(set(source_ids))
    for source in sources:
        if not db.execute('SELECT 1 FROM items WHERE id=?', (source,)).fetchone():
            raise ValueError('Unknown source item')
    version_id = digest({'config': config, 'sources': sources})
    db.execute('INSERT OR IGNORE INTO eval_versions VALUES (?,?,?)', (version_id, json.dumps(config), json.dumps(sources)))
    return get_version(db, version_id)


def delete_source(db, item_id):
    """Called inside the memory deletion transaction, before removing the item."""
    initialize(db)
    invalid = [row[0] for row in db.execute('SELECT id,sources FROM eval_versions') if item_id in json.loads(row[1])]
    for version_id in invalid:
        db.execute('DELETE FROM eval_runs WHERE baseline=? OR candidate=?', (version_id, version_id))
        db.execute('DELETE FROM eval_active WHERE version_id=?', (version_id,))
        db.execute('DELETE FROM eval_history WHERE version_id=?', (version_id,))
        db.execute('DELETE FROM eval_versions WHERE id=?', (version_id,))
    # Saved outputs can contain private information even when the version has no sources.
    # Conservatively erase every report on any source deletion.
    db.execute('DELETE FROM eval_runs')


def delete_all(db):
    initialize(db)
    for table in ('eval_runs', 'eval_active', 'eval_history', 'eval_versions'):
        db.execute('DELETE FROM ' + table)


def normalized_hash(value):
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False)
    return digest(' '.join(unicodedata.normalize('NFKC', text).casefold().split()))


def validate_dataset(dataset, training_examples=()):
    if dataset.get('purpose') != 'heldout_evaluation_only' or dataset.get('origin') != 'synthetic':
        raise ValueError('Only synthetic, evaluation-only holdouts are accepted')
    cases = dataset.get('cases', [])
    if not cases or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Empty or duplicate holdout cases')
    train_ids = {x['id'] for x in training_examples}
    train_hashes = {normalized_hash(x['input']) for x in training_examples}
    train_sources = {source for x in training_examples for source in x.get('source_ids', [])}
    for case in cases:
        if case['id'] in train_ids or normalized_hash(case['input']) in train_hashes or train_sources.intersection(case.get('source_ids', [])):
            raise ValueError('Holdout overlaps training examples by ID or input hash')
    return digest(dataset)


def evaluate(db, baseline_id, candidate_id, dataset, outputs, ratings=None, training_examples=()):
    """outputs: {version_id: {case_id: text}}. Ratings from a human, never inferred.

    ratings: {reviewer, human_reviewed: true, output_origin: saved_model|fixture,
              scores: {version_id: {case_id: {dimension: 1..5}}}}
    Saved-model provenance is an operator attestation, not cryptographic proof.
    """
    initialize(db)
    if baseline_id == candidate_id:
        raise ValueError('Compare distinct versions')
    versions = [get_version(db, v) for v in (baseline_id, candidate_id)]
    training_examples = list(training_examples)
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='items'").fetchone():
        training_examples += [{'id': r[0], 'input': r[1], 'source_ids': [r[0]]} for r in db.execute('SELECT id,conversation FROM items')]
    dataset_hash = validate_dataset(dataset, training_examples)
    case_ids = {c['id'] for c in dataset['cases']}
    if set(outputs) != {baseline_id, candidate_id}:
        raise ValueError('Outputs must contain exactly both compared versions')
    results = {}
    complete = bool(ratings and ratings.get('human_reviewed') is True and str(ratings.get('reviewer', '')).strip())
    for version in versions:
        vid = version['id']
        if set(outputs[vid]) != case_ids:
            raise ValueError('Every holdout case requires one saved output per version')
        checks, scores = {}, {key: [] for key in DIMENSIONS}
        for case in dataset['cases']:
            value = outputs[vid][case['id']]
            if not isinstance(value, str):
                raise ValueError('Saved outputs must be strings')
            rules = case.get('rules', {})
            checks[case['id']] = {
                'nonempty': bool(value.strip()),
                'length': len(value) <= rules.get('max_chars', 1200),
                'questions': value.count('?') <= rules.get('max_questions', 2),
                'forbidden_literals': not any(s.casefold() in value.casefold() for s in rules.get('forbidden_literals', [])),
            }
            grades = (ratings or {}).get('scores', {}).get(vid, {}).get(case['id'], {})
            for dimension in DIMENSIONS:
                score = grades.get(dimension)
                if type(score) is not int or not 1 <= score <= 5:
                    complete = False
                else:
                    scores[dimension].append(score)
        results[vid] = {'rule_checks': checks, 'human_means': {k: sum(v)/len(v) if len(v) == len(case_ids) else None for k, v in scores.items()}}
    metadata = (ratings or {}).get('generation_metadata', {})
    metadata_complete = all(isinstance(metadata.get(v), dict) and all(metadata[v].get(k) for k in ('model', 'prompt_hash', 'generated_at')) for v in (baseline_id, candidate_id))
    if metadata_complete:
        metadata_complete = all(metadata[baseline_id][k] == metadata[candidate_id][k] for k in ('model', 'prompt_hash'))
        if metadata[baseline_id].get('seed') is not None and metadata[candidate_id].get('seed') is not None:
            metadata_complete = metadata_complete and metadata[baseline_id]['seed'] == metadata[candidate_id]['seed']
    if not complete:
        for result in results.values():
            result['human_means'] = dict.fromkeys(DIMENSIONS)
    rules_pass = all(all(check.values()) for check in results[candidate_id]['rule_checks'].values())
    semantic_pass = complete and all(results[candidate_id]['human_means'][k] >= 4 and results[candidate_id]['human_means'][k] >= results[baseline_id]['human_means'][k] for k in DIMENSIONS)
    report = {
        'dataset_hash': dataset_hash, 'dataset_version': dataset.get('version'),
        'outputs_hash': digest(outputs), 'ratings_hash': digest(ratings),
        'generation_metadata': (ratings or {}).get('generation_metadata', {}),
        'training_manifest_hash': digest(list(training_examples)),
        'baseline': baseline_id, 'candidate': candidate_id, 'case_count': len(case_ids),
        'results': results, 'human_review_complete': complete,
        'output_origin': (ratings or {}).get('output_origin', 'unverified'),
        'eligible': bool(rules_pass and semantic_pass and metadata_complete and (ratings or {}).get('output_origin') == 'saved_model'),
        'limits': 'Offline rules and declared human judgments only; no model called, no proven real-world improvement. Fixture ratings never qualify for promotion.',
    }
    report['id'] = digest(report)
    db.execute('INSERT OR IGNORE INTO eval_runs VALUES (?,?,?,?)', (report['id'], baseline_id, candidate_id, json.dumps(report)))
    return report


def bump_revision(db):
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadata'").fetchone():
        db.execute("UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")


def promote(db, version_id, run_id, *, approved=False):
    initialize(db)
    if approved is not True:
        raise ValueError('Explicit promotion approval required')
    get_version(db, version_id)
    row = db.execute('SELECT report FROM eval_runs WHERE id=?', (run_id,)).fetchone()
    if not row:
        raise ValueError('Evaluation absent or invalidated')
    report = json.loads(row[0])
    unsigned = {k: v for k, v in report.items() if k != 'id'}
    if digest(unsigned) != run_id or report['id'] != run_id:
        raise ValueError('Evaluation integrity failure')
    if not report['eligible'] or report['candidate'] != version_id or report['baseline'] != get_active(db)['id']:
        raise ValueError('Promotion requires qualifying human-reviewed comparison against current active version')
    db.execute('INSERT INTO eval_history(version_id) VALUES (?)', (get_active(db)['id'],))
    db.execute('INSERT OR REPLACE INTO eval_active VALUES (1,?)', (version_id,))
    bump_revision(db)
    return get_active(db)


def rollback(db, *, approved=False):
    initialize(db)
    if approved is not True:
        raise ValueError('Explicit rollback approval required')
    row = db.execute('SELECT sequence,version_id FROM eval_history ORDER BY sequence DESC LIMIT 1').fetchone()
    if not row:
        raise ValueError('No retained previous version')
    version = get_version(db, row[1])
    db.execute('INSERT OR REPLACE INTO eval_active VALUES (1,?)', (version['id'],))
    db.execute('DELETE FROM eval_history WHERE sequence=?', (row[0],))
    bump_revision(db)
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, help='Existing Réplique memory SQLite file')
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('candidate'); create.add_argument('--config', required=True); create.add_argument('--source', action='append', default=[])
    sub.add_parser('active')
    ev = sub.add_parser('evaluate')
    for name in ('baseline', 'candidate', 'dataset', 'outputs', 'training-manifest'):
        ev.add_argument('--' + name, required=True)
    ev.add_argument('--ratings')
    pr = sub.add_parser('promote'); pr.add_argument('--version', required=True); pr.add_argument('--run', required=True); pr.add_argument('--approve', action='store_true')
    rb = sub.add_parser('rollback'); rb.add_argument('--approve', action='store_true')
    args = parser.parse_args()
    load = lambda p: json.loads(Path(p).read_text())
    # Do not silently create an unrelated empty database or enable personal memory.
    db = sqlite3.connect(Path(args.db).resolve().as_uri() + '?mode=rw', uri=True)
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            initialize(db)
            if args.command == 'active': result = get_active(db)
            elif args.command == 'candidate': result = create_version(db, load(args.config), args.source)
            elif args.command == 'evaluate': result = evaluate(db, args.baseline, args.candidate, load(args.dataset), load(args.outputs), load(args.ratings) if args.ratings else None, load(args.training_manifest))
            elif args.command == 'promote': result = promote(db, args.version, args.run, approved=args.approve)
            else: result = rollback(db, approved=args.approve)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        db.close()

if __name__ == '__main__':
    main()
