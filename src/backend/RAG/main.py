from langchain_community.document_loaders import DirectoryLoader, UnstructuredFileLoader

loader = DirectoryLoader(
    path= "rag_data"
)