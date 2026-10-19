# Conversation quality changes · 18 October 2026

## Implemented
- One generation contract shared by the compatible API and ChatGPT OAuth path. It retains the original conversation and adds ordered, attributed turns, the last message, and a count of trailing user messages. These remain untrusted user data, outside the instruction prompt.
- Optional backward-compatible `locale` (`fr_neutre`, `afrique_ouest`, `burkina_faso`) and `familiarity` (`neutre`, `familier`) fields. Defaults are neutral. Locale is a user-selected context, not an inferred identity or a dialect generator. The conversation's established expressions and register take priority.
- Instructions prioritize the actual last message, speaker attribution, negation, unknown user facts, short natural wording and useful differences between choices. Short replies do not establish coldness or attraction. Refusals take priority over requests to relaunch a conversation.
- All-empty replies are permitted as a consistent no-send choice. Mixed empty/nonempty replies still fail. Superficial punctuation/case-only variants fail validation.
- Deterministic examples for brief responses and repeated unanswered messages. Repeated unanswered messages now produce three optional, copyable alternatives anchored in the available conversation, followed by advice to choose at most one and leave space; silence alone is not treated as refusal. The demonstration explicitly remains prewritten; regional settings are not a claim of model understanding.
- Limited local refusal heuristics now ignore balanced quotations and distinguish selected specific-topic refusals/counterproposals from global refusals. They still are not semantic understanding.

## Verification
`python -m unittest discover -s backend -t . -v`: **84 tests passed** after the 18 October contextual-follow-up correction, including all prior OAuth, token, origin, timeout, schema and OCR tests. See `backend-v031-tests.log`. The earlier `backend-v03-tests.log` records the historical 82-test run.

The quality/contract tests cover supported/default settings, structured multiline turns, final-message anchoring, unanswered-message count, ambiguous replies, specific refusals, quoted refusals, deterministic examples, abstention, superficial duplicates and injection isolation across both providers. Network provider responses are simulated. Injection isolation tests verify the payload boundary, not a real model's resistance to injection.

`backend/evals/conversation_cases.json` contains **15 synthetic acceptance cases not yet run against a real model**. Each lists required and prohibited behavior. Use it only after a provider/model and any data sharing or cost have been explicitly authorized. Judge groundedness, naturalness, useful variation and boundaries separately; obtaining a reply is not the success metric.

## Evidence and limits
The language approach is informed by situated sociolinguistic research, not a universal African messaging style:
- [Nacro, 1988, French in Burkina Faso](https://www.persee.fr/doc/cls_0758-4156_1988_num_13_2_1030): historical linguistic diversity; not contemporary usage statistics.
- [Napon, 2001, youth groups in Ouagadougou](https://journals.openedition.org/etudesafricaines/116?file=1): situated repertoires; indexed excerpts consulted, not the full article.
- [Sangaré, 2008, greetings in Darsalamy](https://www.memoireonline.com/12/13/8177/Approche-ethnolinguistique-des-formules-de-salutation-chez-les-Dioula-de-Darsalamy-au-Burkina-Faso.html): a local oral field study, not evidence for mandatory greetings in modern chat.
- [Cambridge, Ivorian French and Nouchi](https://www.cambridge.org/core/books/abs/youth-language-practices-and-urban-language-contact-in-africa/exploring-hybridity-in-ivorian-french-and-nouchi/71CBA38840CFCC2BDE8712FDF5755877): publisher abstract situates nouchi in Côte d’Ivoire; not a Burkina-wide register.

No real model quality, authentication or paid generation was tested. Schema checks cannot establish factual accuracy, cultural naturalness or complete safety. Quoted speech, sarcasm, unmarked speakers and long histories can still be ambiguous. Real quality should be reviewed with voluntary speakers from the intended audience using synthetic or authorized anonymized examples.

## Audit follow-up
Explicit local boundaries now cover « Arrête de me contacter », « Je ne veux plus que tu me contactes » and « Je préfère qu’on arrête ». Clause endings avoid treating « te voir triste », « continuer cette dispute » or « plus tard que 18 h » as global contact refusals. A small explicit-language output filter covers selected threats, pressure and unsupported diagnoses in replies, explanations and insight. These are regression protections, not an exhaustive classifier. Fabricated availability and paraphrased threats still require model evaluation and human review; no general semantic detector is claimed.


## User-directed policy correction · 18 October 2026

The earlier implementation chose abstention after repeated unanswered messages. That was a cautious product choice, not an empirical conclusion established by the sources above. The user clarified that ordinary silence should still yield an optional contextual idea, followed by advice to leave some space: someone may have forgotten to reply. The source summaries and their original limitations remain unchanged.

The current prompt and deterministic unanswered-message example follow that correction. They neither diagnose disinterest nor assert that forgetting occurred, and they do not assume how much time has elapsed. With only « On se reparle plus tard » available, an example is « On reprend notre discussion quand tu veux. » The three alternatives are choices, never a sequence or an automatic follow-up schedule. User intentions to decline or set a limit remain respected.

Explicit stop-contact requests still produce no message to send; explicit refusals are not overridden. Coherent abstention remains valid for dangerous, incoherent or insufficient context, so the validator does not require nonempty suggestions universally. Additional regression tests check the ordinary-silence behavior, user closing intent and the prompt distinction; additional synthetic acceptance cases cover a concrete book-choice topic, silence after a stop-contact request and a closing intention. These are policy and contract checks, not evidence of live model quality.
