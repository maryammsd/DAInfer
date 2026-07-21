"""
Sentence-type classification utilities.

This reuses the simple/complex/compound detection logic from the user's
original clause-analysis module, with one addition: `_tokens_from_doclike`,
which was referenced but never defined in the original code, and a single
`classify_sentence_type()` entry point that picks ONE label per sentence
using a priority order (compound > complex > simple), since a sentence can
technically trigger more than one of the underlying boolean checks.
"""

import spacy

nlp = spacy.load("en_core_web_sm")


def _tokens_from_doclike(doc):
    """
    Normalizes access to tokens whether `doc` is a spaCy Doc or a Span.
    NOTE: this was referenced in the original code but not defined there.
    If sentences should be evaluated per spaCy sentence (doc.sents) rather
    than as a whole blob, iterate sentences before calling these functions
    instead of changing this helper.
    """
    return list(doc)


def is_simple_sentence(doc):
    """
    True when no coordinating conjunctions/conjuncts and no subordinate/clausal
    dependencies.
    """
    tokens = _tokens_from_doclike(doc)
    has_cc = any(t.dep_ == "cc" for t in tokens)
    has_conj = any(t.dep_ == "conj" for t in tokens)
    has_subord = any(t.dep_ in ("mark", "relcl", "advcl", "ccomp", "xcomp", "acl") for t in tokens)
    return not (has_cc or has_conj or has_subord)


def is_complex_sentence(doc):
    """
    True when there is any subordinating marker / clausal dependency.
    """
    tokens = _tokens_from_doclike(doc)
    return any(t.dep_ in ("mark", "relcl", "advcl", "ccomp", "xcomp", "acl") for t in tokens)


def is_compound_sentence(doc):
    """
    True when there is a coordinating conjunction or a conjunct token.
    """
    tokens = _tokens_from_doclike(doc)
    return any(t.dep_ in ("cc", "conj") for t in tokens)


def classify_sentence_type(text: str) -> str:
    """
    Returns exactly one of: "simple", "complex", "compound", "unknown".

    Priority order: compound > complex > simple. A sentence with both a
    coordinating conjunction AND a subordinate clause (e.g. "Sets X and
    returns Y if Z is true") is labeled "compound" here, since is_compound
    and is_complex are not mutually exclusive in the original checks.
    Change the order below if you want complex to win ties instead.
    """
    if not text or not text.strip():
        return "unknown"

    doc = nlp(text.strip())

    if is_compound_sentence(doc):
        return "compound"
    if is_complex_sentence(doc):
        return "complex"
    if is_simple_sentence(doc):
        return "simple"
    
    if len(doc) == 0 or len(doc) <= 50:  # arbitrary threshold for "empty" or "too short to classify"
        return "empty"
    
    return "unknown"
