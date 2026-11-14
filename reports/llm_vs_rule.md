# LLM vs rule-search vs baseline

| Video | Ratio | Baseline | Rule | LLM | LLM-Rule | LLM candidate | LLM err |
|---|---|---|---|---|---|---|---|
| 01_FourPeople | 2% | 39.829 | 39.873 | 39.625 | -0.248 | llm-llm | 1.90% |
| 01_FourPeople | 5% | 41.310 | 41.297 | 41.254 | -0.043 | llm-llm | 0.36% |
| 02_Beauty | 2% | 38.574 | 38.679 | 38.613 | -0.066 | llm-llm | 0.00% |
| 02_Beauty | 5% | 39.476 | 39.548 | 39.466 | -0.082 | llm-llm | 1.60% |
| 03_Bosphorus | 2% | 36.946 | 36.991 | 36.893 | -0.098 | llm-llm | 0.05% |
| 03_Bosphorus | 5% | 40.097 | 40.170 | 40.156 | -0.014 | llm-llm | 0.62% |
| 04_HoneyBee | 2% | 41.849 | 41.832 | 41.553 | -0.279 | llm-llm | 1.83% |
| 04_HoneyBee | 5% | 42.400 | 42.396 | 42.312 | -0.084 | llm-llm | 2.24% |
| 07_Mobcal | 2% | 34.402 | 34.409 | 33.797 | -0.612 | llm-llm | 1.72% |
| 07_Mobcal | 5% | 35.792 | 35.805 | 35.440 | -0.365 | llm-llm | 0.01% |
| 08_Shields | 2% | 33.904 | 33.905 | 33.405 | -0.500 | llm-llm | 1.07% |
| 08_Shields | 5% | 35.185 | 35.174 | 34.854 | -0.320 | llm-llm | 0.06% |

## Summary

- cases: 12
- mean LLM - rule: -0.226 dB
- LLM better: 0/12
- decision sources: {'llm': 21}
