from multiprocessing import util
import spacy
import re

nlp = spacy.load("en_core_web_sm")

conjunction_groups = {
        "cause/effect": ["because", "since", "as", "so that", "in order that"],
        "time": ["after", "before", "when", "while", "until", "as soon as"],
        "condition": ["if", "unless", "whether", "provided that"],
        "contrast/concession": ["although", "though", "even though", "whereas"],
        "purpose": ["so that", "in order that"],
        "comparison": ["than", "as"]
    }

#---------------------------------------------------
# Check location of conjunction in the sentence
#---------------------------------------------------
def check_conjunction_location(doc, start_index, conj_token):
    if conj_token.i == start_index:
        return 1
    elif conj_token.i == len(doc) - 1:
        return 3
    elif 0 < conj_token.i < len(doc) - 1:
        return 2
    return 0

#----------------------------------------------------
# Check if a sentence is a simple sentence
#--------------------------------------------------
def is_simple_sentence(doc):
    """
    True when no coordinating conjunctions/conjuncts and no subordinate/clausal dependencies.
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

def remove_parentheses(span):
    """Remove parentheses and their content from a span."""
    text = span.text
    stack = []
    result = []
    skip = 0

    for char in text:
        if char == '(':
            stack.append(char)
            skip += 1
        elif char == ')':
            if stack:
                stack.pop()
                skip -= 1
        else:
            if skip == 0:
                result.append(char)

    return nlp(''.join(result).strip())


def retrieve_comma_clauses(doc, start_index):
    clauses = []
    for token in doc:
        if token.text == ',':
            clause = doc[start_index:token.i].text.strip()
            # check if the clause has a verb
            if any(t.pos_ == "VERB" for t in nlp(clause)):
                clauses.append(clause)
                start_index = token.i + 1

    return clauses

#---------------------------------------------------
# Determine conjunction type based on its text
#---------------------------------------------------
def determine_conjunction_type(conj_text):
    for group, conjunctions in conjunction_groups.items():
        if conj_text.lower() in conjunctions:
            return group
    return "unknown"

def find_negated_verb(clause):
    doc = nlp(clause)
    for token in doc:
        if token.dep_ == "neg" and token.head.pos_ == "VERB":
            return True
    return False

#---------------------------------------------------
# Get relevant clauses based on conjunction group
#---------------------------------------------------
def get_relevant_clauses(conjunction_group, clause_1, clause_2):
    if conjunction_group in ["cause/effect", "condition", "contrast/concession", "purpose", "comparison"]:
        return clause_1
    elif conjunction_group == "time":
        return (clause_1, clause_2)
    return None

#---------------------------------------------------
# Retrieve clauses from the document based on conjunction position
#---------------------------------------------------
def retrieve_clauses_cc(doc, start_index, conj_token):
    pos = check_conjunction_location(doc, start_index, conj_token)
    if pos == 1:
        clause_1 = doc[start_index:conj_token.i + 1].text.strip()
        clause_2 = doc[conj_token.i + 1:].text.strip()
        if clause_1 and clause_2:
            clause_2_has_verb = any(t.pos_ == "VERB" for t in doc[conj_token.i + 1:])
            if clause_2_has_verb:
                return clause_1, clause_2
            else:
                return doc[start_index:].text.strip(),""
    elif pos == 2:
        clause_1 = doc[start_index:conj_token.i].text.strip()
        clause_2 = doc[conj_token.i:].text.strip()
        if clause_1 and clause_2:
            clause_1_has_verb = any(t.pos_ == "VERB" for t in doc[start_index:conj_token.i])
            clause_2_has_verb = any(t.pos_ == "VERB" for t in doc[conj_token.i:])
            if clause_1_has_verb and clause_2_has_verb:
                return clause_2, clause_1
            else:
                return doc[start_index:].text.strip(),""
    return "",""

def split_by_semicolon(sentence):
    """
    Split a sentence by semicolons (;).
    
    Args:
        sentence (str): The input sentence.
    
    Returns:
        list: A list of parts split by semicolons.
    """
    parts = sentence.split(";")
    return [p.strip() for p in parts if p.strip()]

def clause_starts_with_verb(clause_text, nlp):
    if not clause_text:
        return False
    doc = nlp(clause_text)
    if len(doc) == 0:
        return False
    first = doc[0]
    # primary check: POS or tag indicates verb
    if first.pos_ == "VERB" or first.tag_.startswith("VB") or first.pos_ == "AUX":
        return True
    # fallback: lowercase first token and reparse (helps "Returns ..." fragments)
    if first.text and first.text[0].isupper():
        cand = first.text.lower() + ((" " + " ".join([t.text for t in doc[1:]])) if len(doc) > 1 else "")
        doc2 = nlp(cand)
        if len(doc2) > 0 and (doc2[0].pos_ == "VERB" or doc2[0].tag_.startswith("VB") or doc2[0].pos_ == "AUX"):
            return True
    return False

def remove_parentheses_and_null(text):
    """
    Remove all parentheses (including nested) and their contents, normalize spaces,
    and return an empty string when the remaining text is empty or only 'null'.
    """
    if not text:
        return ""
    s = str(text)

    # remove nested parentheses by repeating until none left
    while re.search(r'\([^()]*\)', s):
        s = re.sub(r'\([^()]*\)', '', s)

    # collapse whitespace and trim
    s = re.sub(r'\s+', ' ', s).strip()

    # strip leading/trailing punctuation common in descriptions
    s = re.sub(r'^[\-\–\—\:\;\,\.]+\s*', '', s)
    s = re.sub(r'\s*[\-\–\—\:\;\,\.]+$', '', s)

    # if remaining is empty or just "null" (case-insensitive) return empty
    if not s or s.lower() == "null":
        return ""

    return s

def process_sentence_for_independent(sent):
    """
    Process a single sentence to extract only independent clauses.
    Returns (split_clauses, verbs_per_clause).
    Ensures fragments like "Returns the value" yield clause "return the value"
    and verbs_per_clause contains ["return"].
    """
    # ensure nlp is available
    nlp = globals().get("nlp")
    if nlp is None:
        nlp = spacy.load("en_core_web_sm")
        globals()["nlp"] = nlp

    # get text
    sent_text = sent.text if hasattr(sent, "text") else str(sent)

    # clean noise if helpers exist
    if "remove_parentheses_and_null" in globals():
        sent_text = remove_parentheses_and_null(sent_text)
    if "strip_leading_method_noise" in globals():
        sent_text = strip_leading_method_noise(sent_text)
    sent_text = sent_text.strip()
    if not sent_text:
        return [], []

    doc = nlp(sent_text)

    # mark dependent clause token indices (mark, relcl)
    dependent_token_indices = set()
    for token in doc:
        if token.dep_ in ("mark", "relcl"):
            target_node = token.head if token.dep_ == "mark" else token
            if not any(t.pos_ == "VERB" for t in target_node.subtree):
                target_node = token.head
            for t in target_node.subtree:
                dependent_token_indices.add(t.i)

    independent_tokens = [t for t in doc if t.i not in dependent_token_indices]
    independent_clause = " ".join(t.text for t in independent_tokens).strip()

    # cleanup clause
    if "clean_clause" in globals():
        independent_clause = clean_clause(independent_clause)
    else:
        import re
        independent_clause = re.sub(r'\s+', ' ', independent_clause).strip()

    if not independent_clause:
        return [], []

    # split by coordinating conjunctions if helper exists
    if "split_by_cc" in globals():
        split_clauses = split_by_cc(independent_clause)
    else:
        split_clauses = [independent_clause]

    verbs_per_clause = []
    common_verbs = {"return", "get", "set", "insert", "remove", "read", "write", "put", "add", "create", "convert"}

    for idx, clause in enumerate(split_clauses):
        clause = clause.strip()
        clause_doc = nlp(clause)
        verbs = [t.lemma_ for t in clause_doc if t.pos_ in ("VERB", "AUX")]

        # fallback: reparse with lowercased first token (handles "Returns ..." fragments)
        if not verbs and len(clause_doc) > 0:
            first = clause_doc[0].text
            rest = " ".join([t.text for t in clause_doc[1:]]) if len(clause_doc) > 1 else ""
            cand = first.lower() + (" " + rest if rest else "")
            doc2 = nlp(cand)
            verbs = [t.lemma_ for t in doc2 if t.pos_ in ("VERB", "AUX")]
            if verbs:
                split_clauses[idx] = cand
                clause_doc = doc2

        # fallback: accept VB* tags
        if not verbs:
            verbs = [t.lemma_ for t in clause_doc if getattr(t, "tag_", "").startswith("VB")]

        # heuristic: handle "returns"/"gets" etc. even if spaCy failed
        if not verbs and len(clause_doc) > 0:
            tok0 = clause_doc[0].text.lower()
            tok0_base = tok0.rstrip("s")
            if tok0_base in common_verbs:
                verbs = [tok0_base]
                rest = " ".join([t.text for t in clause_doc[1:]]) if len(clause_doc) > 1 else ""
                split_clauses[idx] = tok0_base + (" " + rest if rest else "")

        verbs_per_clause.append(verbs)

    return split_clauses, verbs_per_clause


def retrieve_verbs_from_clauses(clauses):
    verbs = []
    for clause in clauses:
        doc = nlp(clause)
        for token in doc:
            # return the root verb of the clause
            if token.dep_ == "ROOT" and token.pos_ == "VERB":
                verbs.append(token.lemma_)
            # return all verbs 
            #if token.pos_ == "VERB":
            #    verbs.append(token.lemma_)
    return verbs

def is_passive(sentence):
    doc = nlp(sentence)
    return any(token.dep_ in ("auxpass", "nsubjpass") for token in doc)

def get_root_verb(sentence):
    doc = nlp(sentence)
    for token in doc:
        if token.dep_ == "ROOT" and token.pos_ == "VERB":
            return token.lemma_
    return None

def get_other_verbs(sentence):
    doc = nlp(sentence)
    return [token.lemma_ for token in doc if token.pos_ == "VERB" and token.dep_ != "ROOT"]

def get_similarity(verb1, verb2, model):
    emb1 = model.encode([verb1])[0]
    emb2 = model.encode([verb2])[0]
    emb1 = emb1.reshape(1, -1)
    emb2 = emb2.reshape(1, -1)
    return float(util.cos_sim(emb1, emb2))
    

def split_by_cc(sentence):
    """
    Split a sentence by coordinating conjunctions (cc).
    
    Args:
        sentence (str): The input sentence.
    
    Returns:
        list: A list of clauses split by coordinating conjunctions.
    """
    nlp = spacy.load("en_core_web_sm")
    doc = nlp(sentence)
    clauses = []
    start_index = 0
    for token in doc:
            if token.dep_ == "cc":
                # Check if the right clause (after cc) contains a verb
                right_span = doc[token.i + 1:]
                if any(t.pos_ == "VERB" for t in right_span):
                    # Split: add left and right as separate clauses (if left has a verb)
                    left_span = doc[start_index:token.i]
                    if any(t.pos_ == "VERB" for t in left_span):
                        clauses.append(left_span.text.strip())
                    if any(t.pos_ == "VERB" for t in right_span):
                        clauses.append(right_span.text.strip())
                    print("left: " + left_span.text.strip())
                    print("right: " + right_span.text.strip())
                    return clauses  # Stop after first split
                else:
                    # Do not split: keep the whole clause with the phrase after cc
                    whole_span = doc[start_index:]
                    print("whole: " + whole_span.text.strip())
                    clauses.append(whole_span.text.strip())
                    return clauses  # Stop after first cc

    # If no cc or no split, return the whole sentence
    clauses.append(doc.text.strip())
    return clauses

    # If no cc tokens found, return the original sentence
    #if not clauses:
    #    clauses.append(sentence.strip())

    #return clauses


def clean_clause(clause):
    """
    Clean up a clause by removing leading/trailing punctuation and extra spaces.
    
    Args:
        clause (str): The input clause.
    
    Returns:
        str: The cleaned clause.
    """
    # Remove leading/trailing whitespace
    clause = clause.strip()

    # Remove leading punctuation (comma, period, etc.)
    while clause and clause[0] in ",.;:!?":
        clause = clause[1:].strip()

    # Remove trailing punctuation (except period)
    while clause and clause[-1] in ",.;:!?":
        clause = clause[:-1].strip()

    return clause
