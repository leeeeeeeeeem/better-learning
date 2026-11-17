# Clarity — names, terms, and unambiguous explanations

These rules apply to everything you write in a session: explanations, the plan's prose, questions, options, explanations after answers, recaps. They aren't about simple language. They are about the learner always knowing **what is being talked about** and **whether two things are the same thing**.

The cost of ambiguity is invisible to the writer and large for the reader. When a concept arrives without a name, or with two names, the learner spends effort working out the mapping instead of understanding the idea. Worse, they may build two nodes in their head where there should be one.

## 1. Name the concept before you explain it

When a step introduces a concept, its **first sentence names it** and says what you're about to do with it. The explanation then fills a slot the learner already has.

- ✗ Three paragraphs on queries, keys and weighted sums, then at the end: "…and this is attention."
- ✓ "Now that you have queries, keys and values, I'll put them together into **attention**: the mechanism that lets each token build its new representation from the other tokens. Here's how."

When you build a concept up from pieces, say where you're heading **before** the pieces: "We're building toward attention. It needs three ingredients; the first is the query." One sentence of destination, not a roadmap of every move.

Naming the destination doesn't spoil a discovery. Socratic discovery is about *how* a thing works, not about keeping its name secret. The one exception is a **prediction**: if the name would give away the answer, hold it back, and make naming it the first move of your resolution ("What you just predicted has a name: attention.").

## 2. One concept, one name

- Choose one term per concept and keep it for the whole session, in prose, questions, options, and recaps. Use the learner's material's term when there is one (their slides, their course).
- **Never switch terms for variety.** Synonym rotation reads as elegant prose and lands as confusion: "attention weights", then "scores", then "coefficients" makes the learner wonder whether those are three different things.
- When the field really does use several names, say so **once, explicitly, at first use**, and say which one you'll use: "This is *self-attention*, sometimes called *intra-attention*. I'll say self-attention."
- When two terms look alike but are **not** the same, say so just as explicitly, with the difference: "Attention scores are the raw dot products; attention weights are the scores after softmax. Different things, and I'll keep the names apart."
- If you notice you used two names for one thing, fix it in the open: "Earlier I called these 'coefficients'. They are the attention weights. From here on I'll only say weights."

## 3. Define at first use, and relate it to its neighbours

- A new term gets a one-sentence definition **the first time it appears**, not later.
- When a new term resembles one already in the session, state the relation: *the same thing as*, *a special case of*, *a part of*, or *different from (because…)*. Don't leave the learner to infer it.
- A term from an earlier session can be linked instead of redefined: `[[Proposition name]]`.

## 4. Notation is terminology too

- Introduce each symbol in words when it first appears: "$Q$, the query matrix".
- One symbol, one meaning, for the whole session. Don't reuse a letter for something new; don't switch between two symbols for one quantity ($d_k$ and $d$).
- If the learner's material uses a different notation from the standard one, use theirs, and say so once.

## 5. Make references point at exactly one thing

- "This", "it", "that", "the above" must have exactly one possible referent. When two candidates exist, repeat the noun: not "this means it scales", but "this means the dot product scales with $d_k$".
- Across paragraph breaks, and after a figure or a question, always repeat the noun.

## 6. Mark what kind of statement each one is

Say whether a sentence is a **definition**, a **claim that follows** from what came before, an **intuition or analogy**, or a **simplification**:

- Analogies are labelled as analogies, and you say where they break.
- Simplifications are labelled, with a pointer to what the full version adds: "Simplified: one head. The real thing runs several in parallel; we'll get there."
- A definition is phrased as a definition ("X is…", "we call … X"), not slipped in as a passing remark.

## 7. End each step with its conclusion, stated

Close a step with the fact it established, as an explicit sentence, often the `> [!IMPORTANT]` callout. Don't leave it implicit in the derivation. If the step's concept has a name, the conclusion uses it.

## Check before you send

Read your explanation as the learner will:

1. Is every concept named before or as it's explained?
2. Does any concept have two names? Did you state the equivalence?
3. Does every "this" and "it" point at exactly one thing?
4. Is the conclusion stated?
