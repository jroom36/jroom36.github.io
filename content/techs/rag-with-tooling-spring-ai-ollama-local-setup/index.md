---
title: "From Sticky Notes to Smart Answers: RAG Implementation with Spring Boot 4.1 & Spring AI 2.0"
date: 2026-06-23
draft: false
series: "jrom36-notes"
seriesWeight: 3
categories: ["Java", "Spring Boot", "AI", "Qdrant", "Local Ollama", "Spring AI"]
tags: ["Spring AI", "RAG", "Tool Calling", "Ollama", "Qdrant", "Vector Database", "Semantic Search", "Java", "LLM", "Spring Boot", "Embeddings", "qwen2.5"]
description: "Learn how to build an intelligent note-taking application using RAG (Retrieval-Augmented Generation) with Spring Boot 4.1, Spring AI 2.0, and Qdrant vector database. Includes Tool Calling for accurate expense calculations."
ShowToc: true
TocOpen: true
cover:
    image: "cover.png"
    alt: "Learn how to build an intelligent note-taking application using RAG (Retrieval-Augmented Generation) with Spring Boot 4.1, Spring AI 2.0, and Qdrant vector database. Includes Tool Calling for accurate expense calculations."
---

In previous articles, we [integrated](https://jroom36.github.io/techs/sematic-search-ai-qdrant-ollama-qwen3-embedding/) local LLMs for test generation and set up semantic search with Qdrant. Now it's time to tie these ideas together and build a proper RAG application. We'll create a service that can retrieve relevant notes, pass them into an LLM context, and — crucially — use Tool Calling to perform exact calculations. Using monthly expense tracking as our example, we'll see how Spring AI 2.0 and Spring Boot 4.1 help unify search, generation, and external tools into a cohesive, reliable solution.

Let's build something like this:

https://docs.spring.io/spring-ai/reference/concepts.html

![spring-ai-rag](spring-ai-rag.jpg)

### Setting Up Spring AI and Qdrant

We already have a setup for Spring AI: this configuration provides a Model for Ollama embedding evaluation, specifies where Ollama is started and provides configuration for Qdrant — a store where we keep Notes and their embeddings (vectors).

```yaml
spring:
  application:
    name: jroom36-notes
  main:
    web-application-type: reactive
  ai:
    ollama:
      base-url: ${OLLAMA_HOST:http://localhost:11434}
      embedding:
        model: ${EMBEDDINGS_MODEL:qwen3-embedding:4b}
    vectorstore:
      qdrant:
        host: ${QDRANT_HOST:localhost}
        port: ${QDRANT_PORT:6334}
        collection-name: ${QDRANT_COLLECTION:notes}
        content-field-name: payload
        use-tls: false
        initialize-schema: true
```

And we have indexing set up in vector store (Qdrant in our setup) upon Note creation.
We also have an API to retrieve documents based on a prompt provided via REST API.

### Adding the Chat Model

The next step is to combine results and pass them with a custom user prompt to Chat Model.
So we need to introduce Chat Model into our application. Let's extend the existing configuration with `spring.ai.ollama.chat.model` properties:

```yaml
spring:
...
  ai:
    ollama:
    ...
      chat:
        model: qwen2.5:7b
```
In the previous article we used qwen2.5-coder:7b - the problem with this model is that it does not support AI Tooling - It supports it, but instead of calling the tool it will just respond with a response that contains parameters to call. So my recommendation is to start with qwen2.5:7b

```bash
    ollama pull qwen2.5:7b
```

We need to extend pom.xml with dependencies for Spring AI 2.0:

```
    <dependencies>
        ...
        <dependency>
            <groupId>org.springframework.ai</groupId>
            <artifactId>spring-ai-rag</artifactId>
        </dependency>
        ...
    <dependencies>
```

### Implementing the RAG Service

Next, let's extend the controller with the ability to ask questions. This prompt, based on the schema above, should be passed through the RAG model. We need to first pull Notes from the Qdrant store then append the prompt to this context and pass the request to Chat Model:

```java
NotesController

    @GetMapping("/ask")
    public Mono<String> ask(
            @RequestParam String q,
            @RequestParam(defaultValue = "0.5") float threshold,
            @RequestParam(defaultValue = "10") @Min(1) @Max(100) int limit) {
        return ragService.ask(SearchRequest.builder().query(q).topK(limit).similarityThreshold(threshold).build());
    }
```

And let's add a default ChatClient to the Spring Boot Context.

```java
Jroom36NotesApplication
    
    @Bean
    ChatClient chatClient(ChatClient.Builder builder) {
        return builder.build();
    }
```

Next, we need a RagService which will serve `ask` api. Technically, we have [two options](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html) for how we could implement RAG with Spring AI 2.0:
- Using QuestionAnswerAdvisor
- Using RetrievalAugmentationAdvisor

Let's implement with RetrievalAugmentationAdvisor. We need to pass VectorStoreDocumentRetriever as well.

```java
@Service
@AllArgsConstructor
public class RAGService {

    private VectorStore vectorStore;
    private ChatClient chatClient;

    public Mono<String> ask(SearchRequest searchRequest) {
        return Mono.fromCallable(() -> {
            Advisor retrievalAugmentationAdvisor = RetrievalAugmentationAdvisor.builder()
                    .documentRetriever(VectorStoreDocumentRetriever.builder()
                            .similarityThreshold(searchRequest.getSimilarityThreshold())
                            .topK(searchRequest.getTopK())
                            .vectorStore(vectorStore)
                            .build())
                    .queryAugmenter(ContextualQueryAugmenter.builder()
                            .allowEmptyContext(true)
                            .build())
                    .build();

            return chatClient.prompt()
                    .advisors(retrievalAugmentationAdvisor)
                    .user(searchRequest.getQuery())
                    .call()
                    .content();
        }).subscribeOn(Schedulers.boundedElastic());
    }
}
```

### Testing the RAG Pipeline

OK, we can build and run the application and check the curl request for Notes with the 'spent money' query

```
make up
curl 'http://localhost:8080/api/notes/search?q=spent%20money'
```

We will observe documents in the response that are relevant to the search
Next, let's check the result for the new REST API query /ask with RAG support for 'sum spent money'

```
curl 'http://localhost:8080/api/notes/ask?q=sum%20spent%20money&threshold=0.5'

Summed up, you spent approximately $46.00. This includes $13.65 on dinner, $5.70 on lunch, $4.00 for coffee, $5.00 on cola, $2.05 for milk, $9.10 for cinema, and $4.70 on a hat. Additionally, you used about $6.80 for a taxi.
```

Let's verify the response: $13.65 + $5.70 + $4.00 + $5.00 + $2.05 + $9.10 + $4.70 + $6.80 = $51 - but the AI calculates it as $46.00. We could experiment with the prompt and try to switch the model but as an alternative we could use AI Tooling.

### Solving the Accuracy Problem with Tool Calling

https://docs.spring.io/spring-ai/reference/api/tools.html

A model can respond to prompts, but an AI model can also perform side effects. Side effects can be implemented as Tool Calling for AI. This allows AI to request weather information, use a calculator for math operations, or execute 'rm -rf' - yes, you need to pay attention.

We need a specific Math Tool that should solve the task of summarising spent money.

```
@Component
@Slf4j
public class CalculatorTools {
    @Tool(name = "sum_expenses", description = "Sums a list of monetary amounts in dollars and returns the total using exact BigDecimal arithmetic")
    public String sumExpenses(
            @ToolParam(description = "List of dollar amounts as strings, e.g., ['$13.65', '$5.70']") List<String> amounts) {
        log.info("sum_expenses tool called with {}", amounts);
        ...
        return total;
    }
}
```
As you can see, this is a regular Spring component/Bean with a method annotated with:
- org.springframework.ai.tool.annotation.Tool;
- org.springframework.ai.tool.annotation.ToolParam;

You should provide a description for the tool and its parameters. Now we can register this tool with RAGService:

```java
...
            return chatClient.prompt()
                    .advisors(retrievalAugmentationAdvisor)
                    .user(searchRequest.getQuery())
                    .tools(calculatorTools)
                    .call()
                    .content();
...
```

### Verifying the Results

That's all. Let's try to run the app and make the same request:
```
make up
curl 'http://localhost:8080/api/notes/ask?q=sum%20spent%20money&threshold=0.5'
The total amount spent is $51.00.
```
Much better — the exact expected result. You can also check the logs:
```
INFO 86565 --- [jroom36-notes] [oundedElastic-1] i.github.jroom36.notes.CalculatorTools   : sum_expenses tool called with [$13.65, $5.70, $4.00, $5.00, $2.05, $9.10, $4.70, $6.80]
```

As you can see, our CalculatorTools was responsible for providing the correct answer - based on the information taken from the RAG pipeline.

### Conclusion

In this article, we successfully built a complete RAG application by combining three key pieces: semantic search with Qdrant, local LLMs via Ollama, and Tool Calling for precise calculations. We started with a working setup from previous articles, added a Chat Model, and implemented retrieval-augmented generation using Spring AI 2.0's RetrievalAugmentationAdvisor.

The complete source code is available on [GitHub](https://github.com/alexey-yurganov/jroom36-notes). Feel free to experiment, extend, and build your own RAG-powered solutions.

