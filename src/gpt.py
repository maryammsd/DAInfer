from datetime import datetime
import sys


from helper import *
from prompt import *
from openai import AzureOpenAI, OpenAI
import nltk
from collections import Counter
import random
import config
import tiktoken
import embedding
import llms
import os 
import json

response = None
received = False


def retrieveMagicWords(promptMode, n, t1=1):
    """
    Retrieve typical verbs as magic words
    Args:
        promptMode: The mode of prompting. Manual or automatic.
        n: The parameter of self-consistency
        t1: The temperature of the first stage of prompting
    Returns:
        A list of typical verbs as magic words
    """

    results = {}
    if "manualPrompt" in promptMode:
        return {}
    elif "autoPrompt_FourTypes" in promptMode:
        messages = {
            "memory read": readMagicWordQuestion,
            "memory write": writeMagicWordQuestion,
            "deletion upon memory": deleteMagicWordQuestion,
            "insertion upon memory": insertMagicWordQuestion,
        }
    allMagicWords = []

    for i in range(n):
        for k in messages:
            isRecieved = False
            while not isRecieved:
                try:
                    message = messages[k]

                    s = ["AI"]
                    input = [
                        {
                            "role": "system",
                            "content": "You are a good Java programmer and are very good at choosing proper names for Java methods.",
                        },
                        {"role": "user", "content": message},
                    ]

                    #client = OpenAI(api_key=config.global_openai_key)
                    client = AzureOpenAI(
                        api_key=config.global_openai_key,
                        api_version='2024-06-01',
                        azure_endpoint='https://hkust.azure-api.net'
                    )

                    response = client.chat.completions.create(    
                         messages=[
                            {
                                "role": "user",
                                "content":  message,
                            }
                        ],                  
                        model="gpt-4o-mini"
                    )

                    results[k] = response.choices[0].message.content
                    print(results[k])
                    isRecieved = True
                except:
                    error = sys.exc_info()[0]
                    print("API error:", sys.exc_info())

        singleMagicWords = {}
        wordtags = nltk.ConditionalFreqDist(
            (w.lower(), t)
            for w, t in nltk.corpus.brown.tagged_words(tagset="universal")
        )
        for k in results:
            singleMagicWords[k] = []
            words = results[k].split()
            for word in words:
                word = re.sub(r"[^A-Za-z]+", "", word)
                tags = dict(wordtags[word.lower()])
                if word == "":
                    continue
                isVerb = True
                if "VERB" in tags:
                    for tag in tags:
                        print(word, tag, tags[tag])
                        if tags[tag] > tags["VERB"]:
                            isVerb = False
                else:
                    isVerb = False
                if isVerb:
                    singleMagicWords[k].append(word.lower())
        print(singleMagicWords)
        allMagicWords.append(singleMagicWords)
    magicWords = {}
    for k in messages:
        wordScoreDic = {}
        for singleMagicWords in allMagicWords:
            cnt = 1
            print(singleMagicWords)
            for word in singleMagicWords[k]:
                cnt += 1
                if word not in wordScoreDic:
                    wordScoreDic[word] = 1.0 / cnt
                else:
                    wordScoreDic[word] += 1.0 / cnt
        print("wordScoreDic", wordScoreDic)
        magicWords[k] = max(wordScoreDic, key=wordScoreDic.get)
    print(magicWords)
    return magicWords


#### Added By Maryam
def retrieveAliasRelationwithLLM(
        className: str,
        methodSig1: str,
        methodSig2: str,
        methodDesc1: str,
        methodDesc2: str,
        promptMode: str,
        t2=1.0
    ):
    """ Retrieve alias relations between method parameters and return values
    Args:
        className: The name of the class
        methodSig1: The type signature of the first method
        methodSig2: The type signature of the second method
        methodDesc1: The semantic description of the first method
        methodDesc2: The semantic description of the second method
        promptMode: The mode of prompting. Manual or automatic.
        m: The parameter of self-consistency
        t2: The temperature of the second stage of prompting
    Returns:
        A set of alias parameters with the return values with scores
    """
    result = {}

    if promptMode not in ["alias_zero", "alias_few", "alias_score_zero", "alias_score_few"]:
        print("wrong setting")
        exit(0)
    recieved = False
    tryCnt = 8
    while not recieved:
        try:
            message = getAliasQuestion(
                methodSig1,
                methodSig2,
                methodDesc1,
                methodDesc2,
                promptMode,
           )
            message += f"Above methods are in the same class {className}."
            print("Message:", message)
            input = [
                {"role": "user", "content": message},
            ]

            #client = OpenAI(api_key=config.global_openai_key)

            client = AzureOpenAI(
                    api_key=config.global_openai_key,
                    api_version='2024-06-01',
                    azure_endpoint='https://hkust.azure-api.net'
            )

            response = client.chat.completions.create(    
                    messages=input,                  
                    model="gpt-4o-mini"
            )
            #response = client.chat.completions.create(
            #     model="gpt-3.5-turbo", messages=input, temperature=t2
            #)
            output = response.choices[0].message.content

            print("--------------------------------------------------------")
            print(message)
            print(output)
            print("--------------------------------------------------------")
            tryCnt+=1
                
            #### output processing which is in form of sets of alias parameters, that can be empty set or a set of parameters with/without scores
            # 
            # # Regular expression to match content inside ( and )
            match = re.search(r"\{.*?\}", output)
            if match:
                outputs = match.group()[1:-1]  # Remove the curly braces                    
                recieved = True
                outputs = outputs.split("(")
                if len(outputs) == 0:
                    if outputs == ['']:
                        break;
                    elif outputs.split()[0] == "":
                        break;
                print("Outputs:", outputs)
                for out in outputs:
                    out = out.strip()
                    print("Out:", out)
                    params = out.split(":")
                    # no results found and can be considered as no alias relation
                    if len(params) == 0:
                        break;
                    # there exists some alias relations
                    if promptMode in ["alias_zero", "alias_few"]:
                        for param in params:
                            first_param, second_param = getParameterNamesFromAliasOutput(param)
                            if first_param is not None and second_param is not None:
                                result[(first_param, second_param)] = True
                            elif first_param is not None and second_param is "":
                                result[(first_param, )] = True
                    elif promptMode in ["alias_score_zero", "alias_score_few"]:
                        for param in params:
                            first_param, second_param, score = getParameterNamesFromAliasOutputScore(param)
                            if first_param is not None and second_param is not None and score is not None:
                                result[(first_param, second_param)] = score
                            elif first_param is not None and second_param is None and score is not None:
                                result[(first_param, )] = score
            else:
                config.discarded_alias_queries += 1
                recieved = False
                if tryCnt > 10:
                    break
                continue
            if received:
                # update number of tokens and also the number of prompts already done
                config.LLMTokenCnt += len(tiktoken.encoding_for_model("gpt-4o-mini").encode(message)) + len(tiktoken.encoding_for_mode("gpt-4o-mini").encode(output))
                config.global_num_queries[className] = config.global_num_queries.get(className, 0) + 1
                config.global_num_tokens[className] = config.global_num_tokens.get(className, 0) + len(tiktoken.encoding_for_model("gpt-4o-mini").encode(message)) + len(tiktoken.encoding_for_model("gpt-4o-mini").encode(output))
                if methodDesc1 not in config.global_api_description_set:
                    config.global_api_description_set.append(methodDesc1)
                    config.global_num_descriptions_queried[className] = config.global_num_descriptions_queried.get(className, 0) + 1
                if methodDesc2 not in config.global_api_description_set:
                    config.global_api_description_set.append(methodDesc2)
                    config.global_num_descriptions_queried[className] = config.global_num_descriptions_queried.get(className, 0) + 1
                    
            if tryCnt > 10:
                recieved = False

        except:
            error = sys.exc_info()[0]
            print("API error:", sys.exc_info())
            recieved = False
            if tryCnt > 10:
                break

    return result


def source_vs_sink(arg1: str, arg2: str):
    """ Determine if the dataflow is source or sink
    Args:
        arg1: The first argument
        arg2: The second argument
    Returns:
        Source or Sink or None
    """
    if (arg1 == "0" or int(arg1) > 0) and arg2 == "-1":
        return "Source"
    elif int(arg1) > 0 and arg2 == "0":
        return "Sink"
    return "None"



#### Added By Maryam - a method to parse data-flow inference output
def parseDataFlowInferenceOutput(answer: str):
    """ Parse the output of data flow inference
    """
    flows = set() 
    labels = []
    if answer.startswith("(") and answer.endswith(")"):  
        answer = answer[1:-1]  # Remove the parentheses
        idx = answer.find(')')
        after = answer[idx+1:] if idx != -1 else ''
        output_wo_signature = after.split(",")
        output_wo_signature = output_wo_signature[1:]
        dataflows = ",".join(output_wo_signature).strip().replace(" ", "")
        print("Dataflows:", dataflows)
        if dataflows.startswith("{(") and dataflows.endswith(")}"):
            dataflows = dataflows[1:-1].replace(" ", "")  # Remove the curly braces
            flowList = dataflows.split("),(")
            if len(flowList) == 0:
                if dataflows == '':
                    print("No dataflow")
                    return []
                else:
                    print("One dataflow")
                    arg1, arg2 = dataflows.strip("() ").split(",")
                    labels.append(source_vs_sink(arg1.strip(), arg2.strip()))
                    return labels
            elif len(flowList) > 0:
                print("Multiple dataflows")
                for flow in flowList:
                    print("Flow:", flow)
                    flow = flow.strip("() ")
                    args = flow.split(",")
                    if len(args) == 2:
                        print("Args:", args)
                        arg1 = args[0].strip()
                        arg2 = args[1].strip()
                        flows.add((arg1, arg2))
                # find every tuple in {} in answer , the format of answer is {(arg#i, arg#j),(arg#i,arg#j),...}  
                for flow in flows:
                    arg1, arg2 = flow
                    labels.append(source_vs_sink(arg1.strip(), arg2.strip()))
                  
    return labels

#### Added By Maryam - a method to parse data-flow inference output
def parseDataFlowInferenceTwoMethodsOutput(answer: str, methodname1: str, methodname2: str):
    """ Parse the output of data flow inference
    """
    if answer.startswith("(") and answer.endswith(")"):  
        answer = answer[1:-1]  # Remove the parentheses
        parts = answer[1:-1].split(",")
        if len(parts) >= 3:
            indices = parts[-1].strip()
            if indices.strip("{}").strip():  # Check if there's anything inside the braces
                indices = set(map(int, indices.strip("{}").split(",")))
            else:
                indices = set()  # Default to an empty set if no valid indices are found
            return indices
    return set()

#### Added By Maryam - a method to get data-flow question and perform data-flow specification inference with LLM
def retrieve_dataflow_with_LLM(
    className: str,
    methodSig: str,
    methodDoc: str,
    resultPath: str = "../data/results/dataflow_results/", 
):
    result = set()
    m = 5  # self-consistency parameter set to 5 for the whole analysis
    responses = []
    for i in range(m):
        received = False
        singleResult = set()
        tryCnt = 0
        while not received:
            tryCnt += 1
            try:
                message = getDataFlowQuestion(
                    methodSig,
                    methodDoc,
                    config.promptMode
                )
                message += f"Above method is in class {className}."
                
                before = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                response, token_prompt, token_response = llms.run_llm_model(message)
                after_infer = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                duration = datetime.strptime(after_infer, "%Y-%m-%d_%H-%M-%S") - datetime.strptime(before, "%Y-%m-%d_%H-%M-%S")
                
                # update the time taken for LLM inference
                config.LLMTime += duration.total_seconds()

                if type(token_prompt) is list:
                    token_prompt = len(token_prompt)
                else:   
                    token_prompt = int(token_prompt)
                if type(token_response) is list:
                    token_response = len(token_response)
                else:
                    token_response = int(token_response)

                # update the number of tokens and also the number of prompts already done
                config.LLMTokenCnt += token_prompt + token_response
                config.LLMInputTokenCnt += token_prompt
                config.LLMOutputTokenCnt += token_response

                if response is not None:
                    responses.append(response)
                    if len(response) > 0:
                        answer = response
                        if answer:
                            print("--------- Dataflow Inference Output ---------")
                            print(answer)
                            print("--------------------------------------------------------")
                            config.global_num_queries[className] = config.global_num_queries.get(className, 0) + 1
                            config.global_num_tokens[className] = config.global_num_tokens.get(className, 0) + token_prompt + token_response
                            singleResult = parseDataFlowInferenceOutput(answer)
                            received = True
                            print("Single Result:", singleResult)
                    else:
                        print(f"Empty response received for {message}")
                if received:
                    if singleResult:
                        result = result.union(singleResult)
                        print("Updated Result:", result)
            except Exception as e:
                print("Error:", e)
                received = False
                if tryCnt > 10:
                    break

    # log the response for analysis
    os.makedirs(os.path.join(resultPath, className), exist_ok=True)
    # append the found results for a method to a file, and if not file exists, create one
    with open(os.path.join(resultPath, className, "dataflow_result_prompts.json"), "a") as f:
        print("Writing dataflow results to file...")
        print("Final Result:", result)
        object_to_dump = {
            "className": className,
            "methodSig": methodSig,
            "methodDoc": methodDoc,
            "dataflowResult": list(result),
            "response": str(responses),
        }
        json.dump(object_to_dump, f, indent=4)
    return result

#### Added By Maryam - a method to get similarity of verbs with memory operations
def retrieveVerbMemoryOperationWithEmbeddings(
    model, 
    className: str,
    methodSig: str,
    methodDoc: str,
    m,
    all_verbs,
    t2=1.0,
):
    
    target_operations = {
            "set": "sets value of something.",
            "get": "gets value of something.",
            "insert": "inserts something into a collection.",
            "remove": "removes something from a collection.",
        }

    m = 1
    for i in range(m):
        i = i + 1
        received = False
        tryCnt = 0
        while not received:
            tryCnt += 1
            try:
                input = f"{methodDoc}"
                print("Input to SentenceBERT:", input)
                all_verbs_new = embedding.get_verb_similarity_scores(model,total_verbs=all_verbs, target_operations=target_operations, description=methodDoc)
                if all_verbs_new is None:
                    print("No verbs found")
                    continue
                print("All verbs new:", all_verbs_new)
                if tryCnt > 10:
                    break
                elif len(all_verbs_new) >= len(all_verbs):
                    all_verbs = all_verbs_new 
                received = True
            except:
                error = sys.exc_info()[0]
                print("API error:", error)
                if tryCnt > 10:
                    break
                received = False
    return all_verbs


def retrieveMemoryOperationWithEmbeddings(
    model, 
    className: str,
    methodSig: str,
    methodDoc: str,
    m,
    t2=1.0,
):
    
    target_operations = {
            "set": "write value of something.",
            "get": "access value of something.",
            "insert": "add new item into a collection.",
            "remove": "delete item from a collection.",
        }
    target_operations = {
            "set": "sets value of something.",
            "get": "gets value of something.",
            "insert": "inserts something into a collection.",
            "remove": "removes something from a collection.",
        }


    # Load codebert tokenizer and model
    #tokenizer, model = sentencebert.load_model()   
    operation_score = None
    result = {} 
    m = 1
    for i in range(m):
        i = i + 1
        received = False
        singleResult = {}
        tryCnt = 0
        while not received:
            tryCnt += 1
            try:
                #input = f"Method {methodSig} in class {className} has the following description: {methodDoc}. "
                input = f"{methodDoc}"
                print("Input to SentenceBERT:", input)
                
                operation_score = embedding.predict_operation_sentencebert(model, input, target_operations)
                if operation_score is None:
                    continue
                if tryCnt > 10:
                    break
                if len(operation_score) == 0:
                    continue
                elif len(operation_score) >= 1:
                    for op in operation_score:
                        with open("../data/results/memory_operation_results.txt", "a") as f:
                            f.write(f"Class: {op} with score {operation_score[op]}\n") 
                        singleResult[op] = True
                        print(f"Predicted Memory Operation Type: {op} with score {operation_score[op]}")
                #print("Operation scores:", operation_score)
                received = True
            except:
                error = sys.exc_info()[0]
                if tryCnt > 10:
                    if operation_score is not None:
                        for op in operation_score:
                            singleResult[op] = True
                    else:
                        for op, desc in target_operations.items():
                            singleResult[op] = False
                    break
                print("API error:", sys.exc_info())
                print(" operation_score:", operation_score )
                print(" tryCnt:", tryCnt )
                print(" type of operation_score:", type(operation_score)   )
                received = False
        
        for memoryType,desc in target_operations.items():
            if memoryType not in result:
                result[memoryType] = []
            if memoryType in singleResult:
                result[memoryType].append(singleResult[memoryType])
            else :
                result[memoryType].append(False)


    # apend all the found results for each method and class in a file
    with open("../data/results/memory_operation_results.txt", "a") as f:
        f.write(f"Class: {className}, Method: {methodSig}, Description: {methodDoc} \n {result}\n") 

    for memoryType in result:
        result[memoryType] = Counter(result[memoryType]).most_common()
        print("Memory Type:", memoryType, "Result:", result[memoryType])
        if len(result[memoryType]) == 1:
            result[memoryType] = result[memoryType][0][0]
            if result[memoryType]:
                print(f"[Memory Operation] Final Memory Operation Type {memoryType}")
        else:
            result[memoryType] = random.choice(result[memoryType])[0]
            if result[memoryType]:
                print(f"Random Memory Operation Type for {memoryType}: {result[memoryType]}")
    
    return result

def retrieveMemoryOperationType(
    className: str,
    methodSig: str,
    methodDoc: str,
    magicWords: dict,
    promptMode: str,
    m,
    t2=1.0,
):
    """
    Retrieve memory operation types for the memory operation abstraction
    Args:
        className: The name of the class
        methodSig: The type signature of the method
        methodDoc: The semantic description of the method
        magicWords: The magic words obtained from the first stage of prompting
        promptMode: The mode of prompting. Manual or automatic.
        m: The parameter of self-consistency
        t2: The temperature of the second stage of prompting

    Returns:
        A dictionary of memory operation types
    """

    result = {}
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")

    if "manualPrompt" in promptMode:
        for memoryType in {
            "memory read",
            "memory write",
            "deletion upon memory",
            "insertion upon memory",
        }:
            result[memoryType] = []
    elif "autoPrompt_FourTypes" in promptMode:
        for memoryType in magicWords:
            result[memoryType] = []

    m = 10  # self-consistency parameter set to 10
    for i in range(m):
        received = False
        singleResult = {}
        tryCnt = 0
        while not received:
            tryCnt += 1
            try:
                message = (
                    "Now we provide the specification description of the method "
                    + methodSig
                    + " in the class "
                    + className
                    + " as follows:\n"
                )
                message += methodDoc + "\n"
                message += getQuestion(promptMode)
                answerLength = None
                typeList = None

                if "manualPrompt" in promptMode:
                    systemContent = getInitialPromptForMemoryOperationType(promptMode)
                    answerLength = 4
                    typeList = [
                        "memory read",
                        "memory write",
                        "deletion upon memory",
                        "insertion upon memory",
                    ]
                elif "autoPrompt_FourTypes" in promptMode:
                    systemContent = getInitialPromptForMemoryOperationType(
                        promptMode, magicWords
                    )
                    answerLength = 4
                    typeList = [
                        "memory read",
                        "memory write",
                        "deletion upon memory",
                        "insertion upon memory",
                    ]
                else:
                    print("wrong setting")
                    exit(0)

                input = [
                    {"role": "system", "content": systemContent},
                    # {"role": "system", "content": ""},
                    {"role": "user", "content": message},
                ]

                #client = OpenAI(api_key=config.global_openai_key)

                client = AzureOpenAI(
                        api_key=config.global_openai_key,
                        api_version='2024-06-01',
                        azure_endpoint='https://hkust.azure-api.net'
                )

                response = client.chat.completions.create(    
                        messages=input,                  
                        model="gpt-4o-mini"
                )
                #response = client.chat.completions.create(
                #     model="gpt-3.5-turbo", messages=input, temperature=t2
                #)
                output = response.choices[0].message.content

                print(
                    "OUITPUT:",
                    len(encoding.encode(systemContent)) + len(encoding.encode(message)),
                )
                config.LLMTokenCnt += len(encoding.encode(systemContent)) + len(
                    encoding.encode(message)
                )

                print("--------------------------------------------------------")
                print(message)
                print(output)
                print("--------------------------------------------------------")
                outputs = output.split(",")
                if len(outputs) != answerLength:
                    recieved = False
                    if tryCnt > 10:
                        for memoryType in typeList:
                            singleResult[memoryType] = False
                        break
                    continue

                recieved = True
                i = 0
                for memoryType in typeList:
                    if "no" in outputs[i] or "No" in outputs[i]:
                        singleResult[memoryType] = False
                    elif "yes" in outputs[i] or "Yes" in outputs[i]:
                        singleResult[memoryType] = True
                    else:
                        singleResult[memoryType] = None
                        recieved = False
                    i += 1
            except:
                error = sys.exc_info()[0]
                print("API error:", sys.exc_info())
                recieved = False
                if tryCnt > 10:
                    for memoryType in typeList:
                        singleResult[memoryType] = False
                        break
        for memoryType in singleResult:
            result[memoryType].append(singleResult[memoryType])

    for memoryType in result:
        result[memoryType] = Counter(result[memoryType]).most_common()
        if len(result[memoryType]) == 1:
            result[memoryType] = result[memoryType][0][0]
        else:
            result[memoryType] = random.choice(result[memoryType])[0]
    return result


if __name__ == "__main__":
    loadMagicWords, storeMagicWords = retrieveMagicWords("manualPrompt", 5)
    print(loadMagicWords)
    print(storeMagicWords)
