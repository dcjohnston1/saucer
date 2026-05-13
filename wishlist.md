Problem statement: When i right on an email card, it lets me 'block sender'. However, sometimes I like the sender, but not certain types of email from that sender. For instance, I want Home Depot emails that pertain to my recent order, but not pertaining to promotions. However, it wouldn't be as simple as swiping right and choosing to block sender or block subject, because those subjects are often unique with dates, so blocking one subject wouldn't block future subjects.

Problem solution: 
Saucer — Topic-Based Email Blocking
Currently users can block an entire sender. We need a smarter option: block a type of email from a sender while still allowing other emails from that same sender through. For example, block "Home Depot promotional emails" but allow "Home Depot order updates."
Part 1: UI — Right-Swipe Options
When a user right-swipes an email card, instead of immediately blocking the sender, show a small action menu with two options:

Block Sender — existing behavior, blocks all emails from this address
Block this type — triggers the topic blocking flow (see Part 2)

Part 2: Topic Blocking Flow
When the user taps "Block this type":

Make a Gemini API call with the email subject and first 300 characters of body, and ask: "In 4-6 words, what type of email is this? Be specific but general enough to apply to future similar emails. Examples: 'Home Depot promotional offers', 'school newsletter updates', 'credit card marketing'. Return only the label, nothing else."
Show the user a small confirmation bottom drawer with:

The AI-generated label (e.g. "Home Depot promotional offers")
A text field pre-filled with that label so they can edit it if needed
A "Block this type" confirm button
A "Cancel" button


On confirm, save the rule to a new Firestore collection blocked_topics with fields:

id — unique ID
sender — the sender's email address
label — the human-readable category (e.g. "Home Depot promotional offers")
description — the original Gemini-generated label before any user edits
created_at — timestamp
created_by — user email


Immediately hide the current email from the list (it matches the rule just created)

Part 3: Topic Classification on Incoming Emails
When a new email arrives and passes the sender filter (either via Pub/Sub trigger or /emails fetch), add a topic classification check before passing it to the agent or displaying it:

Check if the sender has any entries in blocked_topics
If yes, make a lightweight Gemini classification call: "Does this email match the topic '{{label}}'? The email subject is '{{subject}}' and preview is '{{first 300 chars}}'. Answer only yes or no."
If yes — dismiss the email silently, log it as email_dismissed with actor: 'gemini' and reasoning: 'Matched blocked topic: {{label}}'
If no — let it through normally

If the sender has no entries in blocked_topics, skip the classification check entirely to avoid unnecessary Gemini calls.
Part 4: Blocked Topics UI in Email Filters Screen
Add a third section to the Email Filters screen called Blocked Topics below Blocked Senders:

List all entries from blocked_topics Firestore collection
Each row shows the sender and the label (e.g. "home depot@email.homedepot.com — Home Depot promotional offers")
Each row has a "Remove" button that deletes the rule from Firestore
No add button needed — rules are created via the swipe gesture only

Part 5: Backend

Add GET /blocked-topics endpoint — returns all blocked topic rules
Add POST /blocked-topics endpoint — creates a new blocked topic rule
Add DELETE /blocked-topics/<id> endpoint — removes a blocked topic rule
Add POST /classify-email-topic endpoint — accepts {email_id, label} and returns {matches: true/false}. This is the lightweight classification call used in Part 3.
Update the email fetching and agent trigger logic to run topic classification before displaying or processing any email from a sender that has blocked topic rules

Testing

Right-swipe a Home Depot promotional email — confirm two options appear: "Block Sender" and "Block this type"
Tap "Block this type" — confirm Gemini generates a label like "Home Depot promotional offers"
Edit the label if needed, confirm — verify entry appears in blocked_topics Firestore collection
Open Email Filters screen — confirm the new rule appears in the Blocked Topics section with a Remove button
Send or sync a new Home Depot promotional email — confirm it gets dismissed silently without appearing in the app
Send or sync a Home Depot order update email — confirm it passes through and appears in the app normally
Remove the blocked topic rule — confirm future Home Depot promotional emails appear againously-ously-