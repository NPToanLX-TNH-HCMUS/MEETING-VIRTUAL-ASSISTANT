# API contract discussion

## Purpose of the contract review

The frontend and backend teams need a common interpretation of document upload before the next integration session. This brief contains two top-level decisions: the upload validation policy and the choice of a staging host. The subsections under validation describe parts of one policy. They should help the group reach a coherent decision rather than become several disconnected agenda items with repeated introductions. The meeting is intended to settle the contract, not to implement a new conversion engine during discussion.

## Discussion items

- Discuss whether PDF and DOCX should be accepted directly.
- Choose a staging host.

## Allowed formats

Discuss whether PDF and DOCX should be accepted directly. The current integration path can work with extracted text, while the product demonstration begins with user documents. The group needs to decide where format checks occur and what the user sees when conversion is unavailable. A file extension alone does not establish whether the content can be read successfully. The discussion should result in a documented validation rule that both sides can explain, including the behavior when a supported-looking document cannot be processed.

## Size checks

The same upload validation policy must explain the size limit. A request that exceeds the limit should produce an understandable result rather than leaving the user unsure whether anything was stored. The frontend can give early feedback, but the backend still needs its own check. This subsection is subordinate to the validation decision above. It is not a request to build a separate storage product or to change every endpoint in the application.

## Validation response agreement

Examples prepared for the review include a normal text document, an oversized upload and a file with an unsupported extension. The interface should be able to distinguish those situations using the agreed response. Participants will walk through the examples as evidence for the policy. They do not need to create a separate agenda item for each sample file. The expected result is one consistent statement of accepted input and failure behavior, with implementation details recorded underneath it.

## Staging host context

Choose a staging host. Two candidate environments are available for the next integration session: a small shared development instance and a separate temporary test instance. The choice should account for who can restart the service, whether the demonstration URL is stable and how test uploads can be cleared afterward. No production customer data is involved. The group should keep this hosting choice separate from upload validation because it has a different owner and can be decided independently.

## Preparation completed

Both teams have received the existing request examples, and the coordinator has confirmed attendance. Those preparation tasks are completed. The notes from this session should capture the two top-level conclusions and their supporting assumptions so that later implementation work uses the same contract.
