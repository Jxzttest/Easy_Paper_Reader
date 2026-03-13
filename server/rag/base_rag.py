
class BaseRAG:
    def __init__(self, retriever, generator):
        self.retriever = retriever
        self.generator = generator

    def retrieve(self, query):
        return self.retriever.retrieve(query)

    def generate(self, query, retrieved_docs):
        return self.generator.generate(query, retrieved_docs)

    def answer(self, query):
        retrieved_docs = self.retrieve(query)
        return self.generate(query, retrieved_docs)