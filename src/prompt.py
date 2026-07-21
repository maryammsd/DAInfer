memoryOperation = (
    "In Java programs, the typical examples over memory are as follows. You can determine which kinds of memory operations conducted by a method call according to"
    "the method name and its specification description. A method might induce multiple operations.\n"
)

memoryOpExamples = [
    '- memory read: If a method name or its specification description contains the word "get" or its synonyms, '
    "the method would read data from inner storage.\n",
    '- memory write: If a method name or its specification description contains the word "set" or its synonyms, '
    "the method would write data to inner storage.\n",
    '- deletion upon memory: If a method name or its specification description contains the word "remove" or its '
    "synonyms, the method would remove data from inner storage.\n",
    '- insertion upon memory: If a method name or its specification description contains the word "put" or its '
    "synonyms, the method would insert data to inner storage.\n",
]

memoryTypeQuestion_manualPrompt = "Please determine whether the method conducts the operation : memory read, memory write, deletion upon memory, and insertion upon memory. Give four yes/no in order as the answers. Do not need give more concrete explanation. Here is the example of output: Yes, No, Yes, Yes. Make sure that the answers are in one line and are seperated by comma.\n"

memoryTypeQuestion_autoPrompt_TwoTypes = "Please determine whether the method conducts the operation : memory read, memory write. Give two yes/no in order as the answer. Do not need give more concrete explanation. Here is the example of output: Yes, No. Make sure that the answers are in one line and are seperated by comma.\n"

memoryTypeQuestion_autoPrompt_FourTypes = "Please determine whether the method conducts the operation : memory read, memory write, deletion upon memory, insertion upon memory. Give four yes/no in order as the answers. Do not need give more concrete explanation. Here is the example of output: Yes, No, Yes, Yes. Make sure that the answers are in one line and are seperated by comma.\n"

writeMagicWordQuestion = "Assume that you are developing a Java method for a Java class. The method stores its parameter to the fields of the Java class. Please list several most-commonly used verbs that can be used in the method name. Remember that the listed words should be valid verbs in the English dictionary. List the verbs seperated by comma. Do not add other sentences. The verbs should be sorted according to your preference. The first one should be the best.\n"

readMagicWordQuestion = "Assume that you are developing a Java method for a Java class. The method loads a value stored in a class field and returns it as the return value. Please list several most-commonly used verbs that can be used in the method name. Remember that the listed words should be valid verbs in the English dictionary. List the verbs seperated by comma. Do not add other sentences. The verbs should be sorted according to your preference. The first one should be the best.\n"

insertMagicWordQuestion = "Assume that you are developing a Java method for a Java class. The method inserts its parameter to the fields of the Java class. Please list several most-commonly used verbs that can be used in the method name. Remember that the listed words should be valid verbs in the English dictionary. List the verbs seperated by comma. Do not add other sentences. The verbs should be sorted according to your preference. The first one should be the best.\n"

deleteMagicWordQuestion = "Assume that you are developing a Java method for a Java class. The method deletes a value from in a class field. Please list several most-commonly used verbs that can be used in the method name. Remember that the listed words should be valid verbs in the English dictionary. List the verbs seperated by comma. Do not add other sentences. The verbs should be sorted according to your preference. The first one should be the best.\n"

#### Added by Maryam - two-methods-dataflow-specification inference with LLM and one few-shot example for retrieving alias between parameters and return value of two methods given the whole class specification
# ------------------------------------------------------------------ Start
alias_relation_class_role_question = (
    "You are a formal program analysis engine. Your task is to analyze a Java class and its method descriptions to output potential object aliasing data-flows. An alias relation exists if an object reference passed into a parameter of a 'store/write' method flows into and is retrieved by a subsequent 'load/read' method. Do not map primitive scalar types (like int, boolean) as aliases. Focus strictly on tracking the data-flow of object instances through the class's internal storage graph. Format your output mapping parameter data-flow to return value indexes.\n"
    "### ANALYSIS RULES\n"
    "1. Pair a 'Store/Write' method (Method A) with a subsequent 'Load/Read' method (Method B).\n"
    "2. Look for object references passed into Method A that flow into internal storage and are later retrieved by Method B.\n"
    "3. Exclude primitive types from being the main aliased object.\n"
    "4. Format your output exactly as a comma-separated list of: alias(<Method A>, <Method B>) = {[Preconditions]-->Postconditions}\n"
    "### SYNTAX KEY\n"
    "- Coordinates use the format (Method_Argument_Index, Target_Slot_Index).\n"
    "- [Preconditions]: Maps matching lookup criteria. `[(1, 1)]` means the 1st parameter of Method A must match the 1st parameter of Method B for the data-flow to execute. For a postcondition, the return value is considered with value 0. The parameters also starts from index 1.\n"
    "- Postconditions: `-->(2, 0)` means the 2nd parameter of Method A flows into the return value of Method B. If you want to refer the return value here, you should use 0. Indexing parameters start from 1.\n"
)

alias_class_few_shots = (
    "Example 1:\n"
    "Class: DataManager\n"
    "Method A: <void setData(Data data, int loc)> with description <The setData(Data data, int loc) method stores the provided Data object into the class's internal storage at the specified location.>\n"
    "Method B: <Data fetchData(int index)> with description <The fetchData(int index) method returns the Data object stored at the specified index in the class's internal storage.>\n"
    "Method C: <String toString()> with description <The toString() method returns a string representation of the DataManager object.>\n"
    "Method D: <void clearData()> with description <The clearData() method removes all data from the class's internal storage.>\n"
    "Method E: <boolean isEmpty()> with description <The isEmpty() method checks if the class's internal storage is empty and returns true if it is, false otherwise.>\n"
    "Answers: alias(<void setData(Data data, int loc)>, <Data fetchData(int index)>) = {[(2, 1)]-->(1, 0)}\n"
    "Example 2:\n"
    "Class: ImageCache\n"
    "Method A: <void putImage(String key, Bitmap bitmap)> with description <The putImage(String key, Bitmap bitmap) method saves the given Bitmap reference into the memory cache mapping it to the specified string key.>\n"
    "Method B: <Bitmap getImage(String key)> with description <The getImage(String key) method searches the cache for the associated key and returns the active Bitmap reference if found.>\n"
    "Method C: <void evictImage(String key)> with description <The evictImage(String key) method looks up the specified key, extracts the object reference from the cache structure to safely recycle it, and then unbinds it.>\n"
    "Method D: <int size()> with description <The size() method returns the current count of cached images.>\n"
    "Answers: alias(<void putImage(String key, Bitmap bitmap)>, <Bitmap getImage(String key)>) = {[(1, 1)]-->(2, 0)}\n"
    "Example 3:\n"
    "Class: java.util.Map\n"
    "Method A: <V put(K key, V value)> with description <The put(K key, V value) method associates the specified value with the specified key in this map, saving the object reference into internal storage.>\n"
    "Method B: <V get(Object key)> with description <The get(Object key) method returns the value object to which the specified key is mapped, or null if this map contains no mapping for the key.>\n"
    "Method C: <V remove(Object key)> with description <The remove(Object key) method looks up the mapping for a key, reads the associated object reference out of the map to return it, and removes the mapping.>\n"
    "Answers: alias(<V put(K key, V value)>, <V get(Object key)>) = {[(1, 1)]-->(2, 0)}, alias(<V put(K key, V value)>, <V remove(Object key)>) = {[(1, 1)]-->(2, 0)}\n"

)


dataflow_methods_role_question = (
    "You are an expert Java programmer. Your task is to analyze Java method descriptions and determine potential data-flow relationships between method parameters and return values to extract data-flow specifications. Our main goal is to see if the consecutive call of two methods has any flows of data between them. The form of data-flow specification is (s, t, {i_1, ... , i_k}), indicating that: when we invoke the method t after method s upon the same object, the value of i_m_th parameter of method s flows to the return value of the method t, while m>= 1 and m<=n for a method s with n parameters. It should be noticed that the index of the parameter starts from 1, while 0 is the index of the return value. \n"
)

#### Added by Maryam - data-flow between the former method's argument with return value of the later method inference with LLM
dataflow_methods_few_shot = """
Example 1: We have two methods for java.util.ArrayList:
- "void add(int index, E element)": "Inserts the specified element at the specified position in this list."
- "E get(int index)": "Returns the element at the specified position in this list."
Then we have the data-flow specification: ("void add(int index, E element)", "E get(int index)", {2}), indicating that the return value of "E get(int index)" may be same with the second parameter of "void add(int index, E element)" if the method get is invoked after the method add.

Example 2: We have two methods for java.util.ArrayList:
- "boolean add(E e)": "Appends the specified element to the end of this list."
- "E get(int index)": "Returns the element at the specified position in this list."
Then we have the data-flow specification: ("void add(E element)", "E get(int ind
ex)", {1}), indicating that the return value of "E get(int index)" may be same with the first parameter of "void add(E element)" if the method get is invoked after the method add.

Example 3: We have two methods for com.google.common.util.concurrent.ForwardingBlockingQueue:
- "boolean offer(E e, long timeout, TimeUnit unit)": "Inserts the specified element into this queue, waiting up to the specified wait time if necessary for space to become available."
- "E poll(long timeout, TimeUnit unit)": "Retrieves and removes the head of this queue, waiting up to the specified wait time if necessary for an element to become available."
Then we have the data-flow specification: ("offer(E e, long timeout, TimeUnit unit)", "E poll(long timeout, TimeUnit unit)", {1}), indicating that the return value of "E poll(long timeout, TimeUnit unit)" may be same with the first parameter of "offer(E e, long timeout, TimeUnit unit)" if the method poll is invoked after the method offer.

Example 4: We have two methods for javax.swing.JComponent:
- "void setActionMap(ActionMap am)": "Sets the ActionMap to am."
- "ActionMap getActionMap()": "Returns the ActionMap used to determine what Action to fire for particular KeyStroke binding."
Then we have the data-flow specification: ("void setActionMap(ActionMap am)", "ActionMap getActionMap()", {1}), indicating that the return value of "ActionMap getActionMap()" may be same with the first parameter of "void setActionMap(ActionMap am)" if the method getActionMap is invoked after the method setActionMap.

Now I will give you the two methods for a given Java class with their descriptions. Please list all the data-flow specification (s, t, {i_1, ... , i_k}) in which i_m represent the position of the arguments in method s that is used to compute the return value of method t. You do not need to add any explanations. Remember to list the correct specifications for the two methods.
"""

#### Added by Maryam - desired output for extracting the data-flow specification
dataflow_methods_output_format = (
    "Your output should be in the following format only: \n"
    "(s, t, {i_1, ... , i_k})\n"
    "If there is no data-flow between the two methods, just answer with an empty set in braces like this (s,t,{}). \n"
)

dataflow_role_question = (
    """
    You are an expert Java programmer. I will provide you with a Java method and its description. Your task is to identify all data-flow relationships within this method.
    For each data-flow, specify which input flows to which output.

    OUTPUT FORMAT:
    (method_signature, {(source, destination), ...})

    POSITION ENCODING:
    - -1 = return value
    - 0 = this (the object the method is called on)
    - 1, 2, 3... = method arguments (by position, starting from 1)

    RULES:
    - If multiple flows exist, list all: {(1, 0), (0, -1)}
    - If no data-flow exists, return an empty set: (method_signature, {})
    - Only output the specification, no explanations.
"""
)

dataflow_few_shot = """
    Here are some examples to illustrate the task and help you understand the output format:
    Example 1 - java.util.ArrayList:
    Method: "void add(int index, E element)" - "Inserts the specified element at the specified position in this list."
    Analysis: The element (arg#2) is stored into this object.
    Specification: (void add(int index, E element), {(2, 0)})

    Example 2 - java.util.ArrayList:
    Method: "boolean add(E e)" - "Appends the specified element to the end of this list."
    Analysis: The element (arg#1) is stored into this object.
    Specification: (boolean add(E e), {(1, 0)})

    Example 3 - java.util.ArrayList:
    Method: "E get(int index)" - "Returns the element at the specified position in this list."
    Analysis: Data stored in this object flows to the return value.
    Specification: (E get(int index), {(0, -1)})

    Example 4 - com.google.common.util.concurrent.ForwardingBlockingQueue:
    Method: "boolean offer(E e, long timeout, TimeUnit unit)" - "Inserts the specified element into this queue, waiting up to the specified wait time if necessary for space to become available."
    Analysis: The element (arg#1) is stored into this object, and the success status (based on this) is returned.
    Specification: (boolean offer(E e, long timeout, TimeUnit unit), {(1, 0), (0, -1)})

    Example 5 - com.google.common.util.concurrent.ForwardingBlockingQueue:
    Method: "E poll(long timeout, TimeUnit unit)" - "Retrieves and removes the head of this queue."
    Analysis: Data from this object flows to the return value.
    Specification: (E poll(long timeout, TimeUnit unit), {(0, -1)})

    Example 6 - javax.swing.JComponent:
    Method: "void setActionMap(ActionMap am)" - "Sets the ActionMap to am."
    Analysis: The ActionMap (arg#1) is stored into this object.
    Specification: (void setActionMap(ActionMap am), {(1, 0)})

    Example 7 - javax.swing.JComponent:
    Method: "ActionMap getActionMap()" - "Returns the ActionMap used to determine what Action to fire for particular KeyStroke binding."
    Analysis: Data from this object flows to the return value.
    Specification: (ActionMap getActionMap(), {(0, -1)})

"""


#### Added by Maryam - Data flow specification inference with LLM
def getDataFlowQuestionMethods(methodsignature1: str, methodsignature2: str, methoddescription1: str, methoddescription2: str, promptMode: str):
    """
    Get the question for data-flow inference between parameters and return value
    Returns:
        The question for data-flow inference
    """
    if "dataflow_llm" in promptMode:
        dataflow_prompt = (
            dataflow_role_question
            + dataflow_few_shot
            + "Here are the two methods and their descriptions:\n"
            + "Method A: <"
            + methodsignature1
            + ">\n"
            "Method B: <"
            + methodsignature2
            + ">\n"
            "Description for A: "
            + methoddescription1
            + "\n"
            "Description for B: "
            + methoddescription2
            + "\n"      
        )
        return dataflow_prompt
    return "error setting"

#### Added by Maryam - Data flow specification inference with LLM
def getAliasQuestionClass(className: str, methodsList: list, descriptionsList: list, promptMode: str):
    """
    Get the question for alias inference between parameters and return value
    Returns:
        The question for alias inference
    """
    if "alias_class" in promptMode:
        alias_prompt = (
            alias_relation_class_role_question
            + alias_class_few_shots
            + "Here are the methods of class "
            + className
            + " and their descriptions:\n"
        )
        for i in range(len(methodsList)):
            alias_prompt += "Method " + chr(65+i) + ": <" + methodsList[i] + "> with description <" + descriptionsList[i] + ">\n"
        return alias_prompt
    return "error setting"
#### ------------------------------------------------------------------ End



#### Added by Maryam - Alias inference with LLM

program_role_question = (
    "You are an expert Java programmer. Your task is to analyze Java method descriptions and determine potential aliasing relationships between method parameters and return values. You are given two methods at a time, and for each method, you need to identify if any of its parameters can be an alias of the others' based on the provided description. What you should consider for finding aliases is the semantically similiar name as well. For instance, if method A is `void setData(Data data, int loc)` and method B is `Data fetchData(int index)`. The description indicates that fetchData returns an object of type Data object at location `index`. It says that setData also sets the value passed to it with location `loc`. You should identify that data parameter in setData and the return value of fetchData are aliases. Also, loc and index serving as location are semantically similar so can be aliases. Your output for this example is a set {(data:'return'),(index:loc:'param')}\n"
)
#### Added by Maryam
alias_question = (
    "List similar parameters by their names separated by comma in a set result = {(parameter_name:parameter_name:'label'), ... } if you find their name similar or aliases. Label indicates if the similarity is between two parameters with 'param' or between a method's parameter and return value of the other with label 'return'. If no, answer with an empty set {}. Just add the final result following the given format in {} and do not explain. \n"
)
#### Added by Maryam
alias_score_question = (
    "Given the method description, for each parameter, provide a score from 0 to 1 indicating the likelihood that the parameter is an alias of the return value or other parameters. If yes, list all such parameters by their names and scores separated by comma in a set result = {(parameter_name:parameter_name:'label':score), ... }. If no, answer with an empty set {}.Just add the final result following the given format in {} and do not explain. \n"
)

#### Added by Maryam
simplify_sentence = (
    "You are a sentence simplification expert. Your task is to break down complex sentences into simple, independent sentences following the below rules."
    "**Rules:**"
    "1. Remove dependent clauses (introduced by if, because, unless, whether, etc.)."
    "2. Split by coordinating conjunctions (and, but, or, nor, etc.)."
    "3. Split by semicolons (;)."
    "4. Keep only independent clauses."
    "5. Ensure each simple sentence is grammatically correct and self-contained."
    "6. Converting the negative sentences to affirmative sentences wherever possible."
    "**Output Format:**"
    "Return a JSON object with the following structure:"
    "{"
    "original_sentence : The original input sentence"
    "simple_sentences: [Simple sentence 1, Simple sentence 2, ...]"
    "}")
    #"**Input:** {input_value}.")


#### Added by Maryam
def getInitialPromptForDataFlowInference_zero_shot(methodsignature: str, methoddescription: str):    
    """
    Get the initial prompt for data flow inference between two methods
    Returns:
        The initial prompt for data flow inference
    """
    initialPrompt = dataflow_role_question 
    initialPrompt += (
        "Here are the  method and its description:\n"
        "Method: <" + methodsignature + ">\n"
        "Description: " + methoddescription + "\n"
    )
    return initialPrompt

def getInitialPromptForDataFlowInference_few_shot(methodsignature: str, methoddescription: str):    
    """
    Get the initial prompt for data flow inference between two methods
    Returns:
        The initial prompt for data flow inference
    """ 
    initialPrompt = dataflow_role_question + dataflow_few_shot 
    initialPrompt += (
        "Here are the  method and its description:\n"
        "Method: <" + methodsignature + ">\n"
        "Description: " + methoddescription + "\n"
    )
    return initialPrompt

#### Added by Maryam

def getDataFlowQuestion(methodsignature: str,methoddescription: str, promptMode: str):
    """
    Get the question for data flow inference between two methods
    Returns:F
        The question for data flow inference
    """
    if "dataflow_zero" in promptMode:
        return getInitialPromptForDataFlowInference_zero_shot(methodsignature=str(methodsignature),methoddescription=str(methoddescription))
    elif "dataflow_few" in promptMode:
        return getInitialPromptForDataFlowInference_few_shot(methodsignature=str(methodsignature),methoddescription=str(methoddescription))

#### Added by Maryam

def getAliasQuestion(methodsignature1: str, methodsignature2: str, methoddescription1: str, methoddescription2: str, promptMode: str):
    """
    Get the question for alias inference between parameters and return value
    Returns:
        The question for alias inference
    """
    if "alias_score_zero" in promptMode:
        return getInitialPromptForAliasInference_score_based_zero_shot(methodsignature1=str(methodsignature1),methodsignature2=str(methodsignature2),methoddescription1=str(methoddescription1),methoddescription2=str(methoddescription2))
    elif "alias_zero" in promptMode:
        return getInitialPromptForAliasInference_zero_shot(methodsignature1=str(methodsignature1),methodsignature2=str(methodsignature2),methoddescription1=str(methoddescription1),methoddescription2=str(methoddescription2))
    elif "alias_few" in promptMode:
        return getInitialPromptForAliasInference_few_shot(methodsignature1=str(methodsignature1),methodsignature2=str(methodsignature2),methoddescription1=str(methoddescription1),methoddescription2=str(methoddescription2))
    
    return "error setting"

#### Added by Maryam
def getInitialPromptForAliasInference_score_based_zero_shot(methodsignature1: str, methodsignature2: str, methoddescription1: str, methoddescription2: str):    
    """
    Get the initial prompt for alias inference between parameters and return value
    Returns:
        The initial prompt for alias inference
    """ 
    initialPrompt = program_role_question + alias_score_question
    initialPrompt += (
        "Here are the two methods and their descriptions:\n"
        "Method A: <" + methodsignature1 + ">\n"
        "Method B: <" + methodsignature2 + ">\n"
        "Description for A: " + methoddescription1 + "\n"
        "Description for B: " + methoddescription2 + "\n"
    )
    return initialPrompt

#### Added by Maryam
def getInitialPromptForAliasInference_zero_shot(methodsignature1: str, methodsignature2: str, methoddescription1: str, methoddescription2: str):    
    """
    Get the initial prompt for alias inference between parameters and return value
    Returns:
        The initial prompt for alias inference
    """ 
    initialPrompt = program_role_question + alias_question
    initialPrompt += (
        "Here are the two methods and their descriptions:\n"
        "Method A: <" + methodsignature1 + ">\n"
        "Method B: <" + methodsignature2 + ">\n"
        "Description for A: " + methoddescription1 + "\n"
        "Description for B: " + methoddescription2 + "\n"
    )
    return initialPrompt

#### Added by Maryam
def getInitialPromptForAliasInference_few_shot(methodsignature1: str, methodsignature2: str, methoddescription1: str, methoddescription2: str):    
    """
    Get the initial prompt for alias inference between parameters and return value
    Returns:
        The initial prompt for alias inference
    """ 
    initialPrompt = program_role_question + alias_question
    initialPrompt += (
        "Here are the two methods and their descriptions:\n"
        "Method A: <" + methodsignature1 + ">\n"
        "Method B: <" + methodsignature2 + ">\n"
        "Description for A: " + methoddescription1 + "\n"
        "Description for B: " + methoddescription2 + "\n"
    )
   
    initialPrompt += (
        "Here are some examples to illustrate the task:\n"
        "Example 1:\n"
        "Method A: <void setData(Data data)>\n"
        "Method B: <Data getData()>\n"
        "Description for A: The getData() method returns the Data object.\n"
        "Description for B: The setData(Data data) method stores the provided Data object into the class's internal storage for later retrieval.\n"
        "Answer: { (data) }\n"
        "Example 2:\n"
        "Method A: <void updateValue(int value)>\n"
        "Method B: <int fetchValue()>\n"
        "Description for A: The updateValue(int value) method updates the internal value with the provided value.\n"
        "Description for B: The fetchValue() method retrieves the current value stored in the class.\n"
        "Answer: {(value)}\n"
        "Example 3:\n"
        "Method A: <void addItem(Item item)>\n"
        "Method B: <Item getItem()>\n"
        "Description for A: The addItem(Item item) method adds the provided Item object to the class's internal storage.\n"
        "Description for B: The getItem() method returns a new Item object created within the method.\n"
        "Answer: {(item)}\n"
    )
    return initialPrompt

def getInitialPromptForMemoryOperationType(promptMode: str, magicWords={}):
    """
    Get the initial prompt for memory operation type
    Args:
        promptMode: The mode of prompting. manualPrompt or autoPrompt_fourTypes
        magicWords: The magic words obtained from the first stage of prompting

    Returns:
        The initial prompt for memory operation abstraction
    """

    if "manualPrompt" in promptMode:
        initialPrompt = memoryOperation
        for example in memoryOpExamples:
            initialPrompt += example
        return initialPrompt
    elif "autoPrompt_FourTypes" in promptMode:
        initialPrompt = memoryOperation
        initialPrompt += (
            "- memory read: If a method name or its specification description contains "
        )
        initialPrompt += magicWords["memory read"]
        initialPrompt += (
            " or its synonyms, the method would read data from inner storage.\n"
        )

        initialPrompt += "- memory write: If a method name or its specification description contains "
        initialPrompt += magicWords["memory write"]
        initialPrompt += (
            " or their synonyms, the method would write data to inner storage.\n"
        )

        initialPrompt += "- deletion upon memory: If a method name or its specification description contains "
        initialPrompt += magicWords["deletion upon memory"]
        initialPrompt += (
            " or their synonyms, the method would remove data from inner storage.\n"
        )

        initialPrompt += "- insertion upon memory: If a method name or its specification description contains the following "
        initialPrompt += magicWords["insertion upon memory"]
        initialPrompt += (
            " or their synonyms, the method would insert data to inner storage.\n"
        )
        return initialPrompt


def getQuestion(promptMode: str):
    """
    Get the question for memory operation abstraction
    Args:
        promptMode: The mode of prompting. manualPrompt or autoPrompt_fourTypes

    Returns:
        The question for memory operation abstraction
    """
    if "manualPrompt" in promptMode:
        return memoryTypeQuestion_manualPrompt
    elif "autoPrompt_FourTypes" in promptMode:
        return memoryTypeQuestion_autoPrompt_FourTypes
    else:
        print("error setting")
        exit(0)


def checkSimilarity(promptMode: str):
    """
    Check whether to use similarity-based filtering
    Args:
        promptMode: The mode of prompting. manualPrompt or autoPrompt_fourTypes

    Returns:
        Whether to use similarity-based filtering
    """
    if "manualPrompt" in promptMode:
        return True
    elif "autoPrompt_FourTypes" in promptMode:
        return False
    else:
        print("error setting")
        exit(0)
