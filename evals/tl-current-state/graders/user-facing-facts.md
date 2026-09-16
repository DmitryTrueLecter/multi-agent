---
type: llm
---

The response describes what a person managing the team meets on the members screen today. Judge it against the fixture's behaviour:

PASS if the description, in a user's terms, covers all of: (1) the list of members with email, role (viewer / editor) and status (Active, or Invited with the number of days); (2) inviting by email with a role, and that inviting someone already present or already invited is refused with a message; (3) an invite accepted after 7 days is refused with a message telling the person to ask for a new invite; (4) changing a member's role and removing a member from the list; (5) the removal question is answered explicitly — either "anyone can remove anyone, nothing checks who removes whom" or that point marked as not settled by the code — one of the two, stated plainly.

FAIL if any of (1)–(5) is missing, if the text explains mechanics (files, functions, status codes, tables — the literal marker "not settled by the code" is not a mechanics mention), if it opens with a preamble about bootstrap or what was read instead of the description itself, or if it proposes how a future feature should work.
