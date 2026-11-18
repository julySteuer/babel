preprocess_grammarinator grammar:
    uv run grammarinator-process `echo {{grammar}}/*.g4` -o out/

generate_grammarinator grammar generator depth test_num:
    uv run grammarinator-generate {{generator}} -r `cat {{grammar}}/startsymbol` -d {{depth}} -o out/gen/test_%d -n {{test_num}} --sys-path out/