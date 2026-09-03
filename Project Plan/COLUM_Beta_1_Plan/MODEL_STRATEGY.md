# COLUM Beta 1 — OpenRouter Model Strategy

## No custom LLM
Beta 1 uses OpenRouter as the model gateway.

## Selection
The model selector should:
1. retrieve/configure current candidate models
2. filter for free availability
3. check context length
4. check tool/function-calling compatibility
5. score reasoning quality
6. consider latency and reliability
7. select the highest-scoring candidate
8. fall back to another candidate on failure

## Important
Free model availability, limits and rankings can change. Therefore model selection must be configuration-driven/dynamic rather than permanently tied to one model ID.

## Future
The same ModelGateway interface can later support:
- local models
- paid models
- a custom COLUM fine-tuned model
without changing the agent/tool architecture.
