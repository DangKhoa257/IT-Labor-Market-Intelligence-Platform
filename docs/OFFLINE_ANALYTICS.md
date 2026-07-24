# Offline Analytics

`analytics.summaries.analyze_records` emits descriptive results for the accepted offline sample: market overview, category, company, city/work-mode, skills and per-record skill co-occurrence, closed states, and salary statistics grouped by currency.

Every artifact includes sample size, generated timestamp, source coverage, and limitations. Salary mean, median, range, and quartiles use only disclosed numeric ranges and are never converted across currencies. The pilot is an input sample, not a market-representative estimate.

The generated artifact is `reports/topdev_pilot_analytics.json`.
