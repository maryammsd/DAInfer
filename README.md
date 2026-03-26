# DAInfer+

This is the official GitHub repository for the following paper:

**DAInfer+: Neurosymbolic Inference of API Specifications from Documentation via Embedding Models.**

This paper is a journal extension of the following paper, which uses Embedding Models to retrieve data-flow specifications for Android and Java APIs:

**DAInfer: Inferring API Aliasing Specifications from Library Documentation via Neurosymbolic Optimization (FSE 2024).**


## Quick Start

### Setup

Step 1: Install the packages listed in `requirements.txt`.

```commandline
pip install -r requirements.txt --use-deprecated=legacy-resolver
```

Step 2: Download the necessary resources for the tagging model. Execute the following code in a Python environment:

```python
> import nltk
> nltk.download('brown')
> nltk.download('universal_tagset')
> nltk.download('averaged_perceptron_tagger')
nltk.download('punkt')
```

Step 3: Download the English model for spaCy:

```
python -m spacy download en_core_web_sm
```

Step 4: Add your OpenAI key in `src/config.py`

```python
global_openai_key = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### Run 

DAInfer+ provides a few capabilities to infer both data-flow and alias specifications for Android and Java APIs using LLMs or embedding models. You can choose any of the following options to run your desired capability through the command line:

```
usage: python run.py [-h] [n] [n] [m] [m] [--easy] [--eager] [--llm] [--llm-dataflow] [--sink-source] [--embed]

optional arguments:
  -h, --help            show this help message and exit
  m: the temperature for GPT
  n: self-consistency parameter used to run a few prompts and select the highest reported results by LLM
  --easy: 
  --eager
  --llm
  --llm-dataflow
  --sink-source
  --embed
 
```
You can configure your desired LLM model and embedding model in the `config.py` by modifying the variables `LLM` and `EMBEDDING_MODEL`. Currently, our tool only supports E5 and SentenceBert models as well as GPT, Qwen, DeppSeek Coder, and DeepSeek V2. We used `ollama` and locally built the open-sourced LLM models on our machine. You need to do the same to use these models. To use GPT, you only need to set the OpenAI key in the variable `openai_key_baseline` in the `config.py` file. 


**Run Alias Spec Inference with two-staged prompting with LLMs.** If you want to run the DAInfer with the default setting to use LLM for retrieving the alias specifications for APIs, you can simply execute the following command:

```commandline
cd src
python run.py 1 1 0.7 0.7 --lazy
```

If you want to disable the lazy strategy in the neural-symbolic optimization, you can replace the `--lazy` flag with `--eager`.

```commandline
cd src
python run.py 1 1 0.7 0.7 --eager
```

ATTENTION: The eager mode would invoke the OpenAI API for a large number of methods documented in the library, which may cost a lot of money. We recommend using lazy mode to avoid the high cost.

**Run Data-Flow Spec Inference with Embedding Model.** If you want to run the DAInfer+ to use embedding models for retrieving the data-flow specifications for APIs, you need to run the command below:

```commandline
cd src
python run.py --source-sink
```

**Run Alias Spec Inference with Embedding Model.**
Next, you can run DAInfer+ with the following command to retrieve only data-flow facts with embedding models for our data-flow dataset:

```commandline
cd src
python run.py 1 1 0.7 0.7 --embed
```

**Run Data-Flow Spec Inference with one-staged prompt with LLMs.** If you want to run the DAInfer+ to use LLMs for retrieving the data-flow specifications for APIs, you should run the command below:

```commandline
cd src
python run.py 1 1 0.7 0.7 --llm-dataflow
```

If you want to apply the self-consistency to the one or two-staged prompting and adjust the temperatures, you can change the four arguments passed to `main.py`. Currently, our tool only supports this for setting the temperature of GPT models. 
For example, if you want to set K = 5 for both the two stages and the temperatures are both set to 1.0, you can execute the following command:

```commandline
cd src
python run.py 5 5 1.0 1.0 --lazy // or
python run.py 5 5 1.0 1.0 -llm-dataflow
```

### Dataset
We parse the documentation of Java classes used for the evaluation and provide the documentation model in the directory `data/javadoc/benchmark-dainfer+`. All the analyzed Java classes are listed in the JSON file `data/javadoc/evalSubject.json`. All the methods and their semantic descriptions are summarized in the JSON file `benchmark_fullMethodDoc.json` for our first paper, DAInfer. For DAInfer+, we used a larger set of Android and Java classes for our experiment. The semantic descriptions of this set are available in the JSON file `benchmark_fullMethodDoc-android.json`.

We provide `docParser.py` in the directory `src`. You can use it to extract the documentation of the Java library you focus on, and then run DAInfer to infer the API data-flow aliasing specifications for the library.

### Oracle

The directory `oracle` contains three sources of oracles: those specified in FlowDroid and USpec, and the manually specified ones. The generated Atlas models are stored in `baseline/atlas/models`. We referred to all the other oracles when we manually specified ours, which is stored in the directory `oracle/ManualOracle` for either alias or data-flow inference.

### Output

The output of DAInfer is stored in the directory `data/output`. Specifically, the directory `autoPrompt_FourTypes_m_n_temp1_temp2` stores the detailed output from DAInfer under the following two-staged prompting setting.

- m and n: The number of samples in self-consistency prompting for the typical verb retrieval and the memory operation abstraction, respectively.

- temp1 and temp2: The temperatures of the prompting for the typical verb retrieval and the memory operation abstraction, respectively.

In each directory `autoPrompt_FourTypes_m_n_temp1_temp2`, the three sub-directories contain the following (intermediate) results:

- The directory `methoInfo`: contains the JSON files that record the method type signatures and the results of memory operation abstraction.

- The directory `prompt` contains the prompting results of the first stage, i.e., the typical verbs indicating the four kinds of memory operations.

- The directory `inferResult`: The results of the API aliasing specification inference. Specifically, the JSON file `benchmark_inferredSpecs.json` contains all the inferred specifications. The JSON file `benchmark_CHADic.json` maintains the class hierarchy relation. The JSON file `benchmark_NNSet.json` contains the identified semantic units, namely named entities in the method names. The JSON file `benchmark_retArgSpecCandidate.json` stores all API aliasing specifications that satisfy the degree and validity constraints, but may not satisfy the semantic unit and memory operation constraints.

- The directory `compareResult`: The comparison results of the inferred specifications and the oracle in the directory `oracle`. Specifically, the JSON files `inferredCorrectSpecs.json` and `inferredWrongSpecs.json` list the correct and incorrect specifications for the 60 Java classes sampled, respectively. The files `missedFlowDroidSpecs.json` and `missedUSpecArgSpec.json` store the specifications that are not inferred by DAInfer but are labeled by FlowDroid's developers or inferred by USpec, respectively.

## Baseline

Apart from Atlas and USpec, we propose an LLM-based API aliasing specification inference approach as a baseline. To run the baseline, you also need to fill in the OpenAI key in the following statement:

```python
openai_key_baseline = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```
Then you can simply run the baseline by executing the following command:

```commandline
cd baseline/LLM-Alias
python ChatGPTBaseline.py
```

The results of the baseline are dumped to the `output.json` file in the directory `baseline/LLM-Alias`.

## Citation

If you use DAInfer in your research, please cite the following paper:

```
@inproceedings{DAInfer,
  author={Chengpeng Wang 
  and Jipeng Zhang 
  and Rongxin Wu 
  and Charles Zhang} ,
  title={DAInfer: Inferring API Aliasing Specifications from Library Documentation via Neurosymbolic Optimization},
  booktitle={The Proceedings of the ACM on Software Engineering},
  volume={1},
  number={FSE},
  year={2024},
  doi = {10.1145/3660816},
```
