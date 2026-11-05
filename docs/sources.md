# Источники и самостоятельная часть

- Источник идеи: [mishasdk/mipt-secure-sql-agents](https://github.com/mishasdk/mipt-secure-sql-agents). README описывает проект практического курса МФТИ с генерацией, проверкой и исправлением PostgreSQL-запросов. В этой работе использована общая идея цикла; исходный код и интерфейс не копировались.
- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api): StateGraph, условные переходы и завершение графа.
- [SQLGlot](https://sqlglot.com/sqlglot.html): разбор, обход и пересборка SQL; проверка имён по схеме.
- [PostgreSQL SET TRANSACTION](https://www.postgresql.org/docs/17/sql-set-transaction.html): семантика read-only транзакций и её пределы.
- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses): JSON Schema и структурированные ответы.
- [OpenAI Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create): формат совместимого адаптера. Реальное подключение провайдера требует отдельной проверки.

Самостоятельная часть: контракт кредитных данных, синтетический набор, словарь финансовых терминов, проверка SQL с разрешающими списками, роль PostgreSQL, ограниченный исполнитель, граф и журнал, адаптеры провайдеров, интерфейс, интеграция с первым проектом и eval-набор.

Собственный код распространяется под MIT. Данные demo синтетические. В интеграционном режиме данные остаются в базе Credit Risk Desk; условия исходного Berka-набора и его атрибуция описаны в первом проекте. В репозиторий Copilot этот набор не включён.

Проект не заявляет принадлежность МФТИ или Т-Банку. Названия вузов и работодателя относятся к исходной идее и контексту портфолио.
