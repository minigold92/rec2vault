# Security

QuietClerk handles meeting audio and transcripts, so data leaks are treated as the most serious kind
of bug.

## Reporting

Please report vulnerabilities privately through GitHub:
**Security → Report a vulnerability** on this repository. Do not open a public issue, and do not
include real recordings, transcripts or notes; a synthetic reproduction is enough.

You can expect a first answer within a week. This is a one-person project, so fixes are made on a
best-effort basis and only the latest commit on `main` is supported.

## What is in scope

- Audio or text leaving the Mac other than to engines and fields the user agreed to
  (`providers.order`, `providers.consent`, `providers.local_only`).
- A text engine being able to run commands, read files or use the network through QuietClerk's
  calls. Codex and Claude are invoked with tools disabled; see
  [What leaves your Mac](docs/how-it-works.md#6-what-leaves-your-mac).
- Instructions spoken in a meeting changing what the pipeline does, beyond the wording of the note.
- The local web screens: anything reachable without the bootstrap token, cross-site requests,
  DNS rebinding, or the server listening on a non-loopback address.
- Files in the inbox that make the pipeline read or write outside its folders (symlinks, crafted
  names, oversized or malformed audio), or delete anything in the Syncthing inbox or vault that it
  did not create.
- Overwriting text the user wrote in a note.

## Out of scope

- What the engine vendors (OpenAI, Anthropic) do with the text they receive under your account.
- Someone with access to your logged-in macOS user account.
- Accuracy of transcripts and summaries; please file those as normal issues.
