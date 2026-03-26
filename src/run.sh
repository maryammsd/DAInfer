#!/bin/bash



# (1) Prepare the environment 
llm_models=( "deepseek-v2:16b") # add gpt-4 when available

# (2) Initiate a tmux session 
tmux new -s llm_analysis_session -d

printf "Started tmux session 'llm_analysis_sessions'\n"

# (3) Set the Python environment and go to src code directory 

printf "Setting up Python environment and navigating to source code directory...\n "
cd /home/maryam/clearblue/source-code/DAInfer/src
source /home/maryam/clearblue/source-code/DAInfer/myenv/bin/activate


# (4) Then, run the analysis for each LLM model in the array for 5 times, one after the other
# (5) Add the llm model name from the arrary to config.llm variable in the config.py file
# (6) Run the following command to start the analysis
for llm_model in "${llm_models[@]}"; do
    for run_id in {1..5}; do
        echo "Running analysis with LLM model: $llm_model, Run ID: $run_id"

        # (5) Modify LLM in config.py file with the current LLM model from the array
        sed -i "s/^LLM\s*=.*/LLM = '$llm_model'/" ./config.py

        # (6) Run the following command to start the analysis
        python3.8 ./run.py 5 $run_id 1.0 1.0 --llm-dataflow

    done
done
