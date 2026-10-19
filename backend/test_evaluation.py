"""Synthetic contract tests, NOT evidence of model quality or human review."""
import copy
import sqlite3
import unittest
from backend import evaluation as ev


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE items(id TEXT PRIMARY KEY, conversation TEXT, expires_at TEXT)')
        self.db.execute("INSERT INTO items VALUES ('source', 'Private context', '2099-01-01')")
        self.db.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)')
        self.db.execute("INSERT INTO metadata VALUES ('revision','0')")
        self.dataset = {'version': 'test-v1', 'origin': 'synthetic', 'purpose': 'heldout_evaluation_only', 'cases': [{'id':'heldout', 'input':'Other: Meet Thursday?', 'rules': {'max_questions': 1, 'max_chars': 100}}]}
        self.candidate = ev.create_version(self.db, {'max_examples': 2, 'max_context_chars': 4000}, ['source'])['id']
        self.outputs = {'builtin': {'heldout': 'Thursday works.'}, self.candidate: {'heldout': 'Thursday works.'}}
        self.ratings = {'reviewer': 'TEST FIXTURE ONLY', 'human_reviewed': True, 'output_origin':'fixture', 'scores': {v: {'heldout': dict.fromkeys(ev.DIMENSIONS, 4)} for v in self.outputs}, 'generation_metadata': {v: {'model':'test-only', 'prompt_hash':'test-only', 'generated_at':'test-only', 'seed':None} for v in self.outputs}}

    def tearDown(self): self.db.close()

    def report(self): return ev.evaluate(self.db, 'builtin', self.candidate, self.dataset, self.outputs, self.ratings)

    def test_no_human_judgment_means_no_semantic_claim_or_promotion(self):
        r = ev.evaluate(self.db, 'builtin', self.candidate, self.dataset, self.outputs)
        self.assertFalse(r['eligible'])
        self.assertFalse(r['human_review_complete'])
        self.assertIsNone(r['results'][self.candidate]['human_means']['naturalness'])
        with self.assertRaises(ValueError): ev.promote(self.db, self.candidate, r['id'], approved=True)

    def test_fixture_cannot_promote(self):
        r = self.report()
        self.assertFalse(r['eligible'])
        with self.assertRaises(ValueError): ev.promote(self.db, self.candidate, r['id'], approved=True)

    def test_promotion_and_rollback_contract_with_simulated_attestation(self):
        # Simulate a caller's declaration to exercise transaction logic only.
        self.ratings['output_origin'] = 'saved_model'
        r = self.report()
        with self.assertRaises(ValueError): ev.promote(self.db, self.candidate, r['id'])
        ev.promote(self.db, self.candidate, r['id'], approved=True)
        self.assertEqual(ev.get_active(self.db)['id'], self.candidate)
        self.assertEqual(self.db.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()[0], '1')
        with self.assertRaises(ValueError): ev.rollback(self.db)
        self.assertEqual(ev.rollback(self.db, approved=True)['id'], 'builtin')
        self.assertEqual(self.db.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()[0], '2')

    def test_deletion_invalidates_outputs_versions_and_rollback(self):
        self.ratings['output_origin'] = 'saved_model'
        r = self.report()
        ev.promote(self.db, self.candidate, r['id'], approved=True)
        ev.delete_source(self.db, 'source')
        self.db.execute("DELETE FROM items WHERE id='source'")
        self.assertEqual(ev.get_active(self.db)['id'], 'builtin')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM eval_runs').fetchone()[0], 0)
        with self.assertRaises(ValueError): ev.get_version(self.db, self.candidate)
        self.assertEqual(ev.rollback(self.db, approved=True)['id'], 'builtin')

    def test_expired_source_never_active(self):
        self.ratings['output_origin'] = 'saved_model'
        r = self.report(); ev.promote(self.db, self.candidate, r['id'], approved=True)
        self.db.execute("UPDATE items SET expires_at='2000-01-01'")
        self.assertEqual(ev.get_active(self.db)['id'], 'builtin')

    def test_overlap_rejected_by_id_normalized_text_source_and_database(self):
        for manifest in ([{'id':'heldout','input':'different'}], [{'id':'different','input':'  OTHER:   meet THURSDAY?  '}], [{'id':'different','input':'different','source_ids':['common']} ]):
            d = copy.deepcopy(self.dataset); d['cases'][0]['source_ids']=['common']
            with self.assertRaises(ValueError): ev.validate_dataset(d, manifest)
        self.dataset['cases'][0]['input'] = ' PRIVATE CONTEXT '
        with self.assertRaises(ValueError): self.report()

    def test_output_set_and_semantic_regression(self):
        self.outputs[self.candidate] = {}
        with self.assertRaises(ValueError): self.report()
        self.outputs[self.candidate] = {'heldout':'Why? When?'}
        self.ratings['output_origin']='saved_model'
        self.assertFalse(self.report()['eligible'])

    def test_immutable_integrity_and_restricted_configs(self):
        with self.assertRaises(ValueError): ev.create_version(self.db, {'code':'eval(unsafe)'})
        self.db.execute('UPDATE eval_versions SET config=? WHERE id=?', ('{"max_examples":0,"max_context_chars":500}', self.candidate))
        with self.assertRaises(ValueError): ev.get_version(self.db, self.candidate)

    def test_dataset_and_output_hashes(self):
        first = self.report()
        self.outputs[self.candidate]['heldout']='Thursday is good.'
        second = self.report()
        self.assertNotEqual(first['outputs_hash'], second['outputs_hash'])
        self.assertEqual(first['dataset_hash'], second['dataset_hash'])

    def test_mismatched_model_blocks_config_comparison(self):
        self.ratings['output_origin']='saved_model'
        self.ratings['generation_metadata'][self.candidate]['model']='different-model'
        self.assertFalse(self.report()['eligible'])

    def test_missing_provenance_blocks_promotion(self):
        self.ratings['output_origin']='saved_model'; self.ratings.pop('generation_metadata')
        self.assertFalse(self.report()['eligible'])

if __name__ == '__main__': unittest.main()
