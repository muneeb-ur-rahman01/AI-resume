# Design decisions

1. **No chatbot-first UI.** Core tasks (review facts, compare requirements, approve applications) are structured
   screens. A conversational assistant may come later for career guidance only.
2. **Fact review before profile.** Extraction results land on a review screen with provenance badges instead of
   silently filling the profile. Likely-correct items are pre-checked (stated, confidence ≥ 0.5); unchecked items
   are recorded as rejected.
3. **Two-step submission.** A confirmation checkbox enables the submit button, which opens a dialog summarizing
   what is shared and how many claims could not be verified.
4. **Relevance, not "match %".** Scores are integers out of 100 with a component breakdown behind a disclosure, to
   avoid false precision.
5. **Employer view is advisory.** The relevance summary sits below the candidate's own materials and carries an
   explicit "must not be the sole basis for a decision" note.
6. **Mock transparency.** Any output from the mock provider shows a warning alert, so screenshots and demos can't
   be mistaken for real AI output.
7. **Status vocabulary.** Candidates see "Not selected" instead of "Rejected".
