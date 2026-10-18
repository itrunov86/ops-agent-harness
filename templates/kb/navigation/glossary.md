# Глоссарий сервисов и синонимов

`kb.py` читает этот список: по нему определяет `services` документа и расширяет поисковый запрос синонимами.
Формат строки: `- канон: синоним, синоним`. Канон — короткое имя в нижнем регистре; его пишут во frontmatter
(`services: [payments]`) и в `kb.py --service payments`. Нового сервиса нет в списке — добавь строку сюда, а не
придумывай имя во frontmatter.

Синонимы сопоставляются по основам слов (русские окончания учитываются). Слишком общие слова («метрики», «логи»,
«сеть») сюда не добавляй: они пометят полбазы.

## Платформа и доставка

- kubernetes: k8s, kube, кубер, кубернетес, kubelet, node group
- argocd: argo cd, argo, арго, applicationset, gitops, гитопс
- helm: хелм, helm chart
- terraform: терраформ, tfstate
- terragrunt: терраграунт
- vault: hashicorp vault, волт, approle

## Наблюдаемость

- prometheus: прометеус, promql
- grafana: графана, дашборд
- alertmanager: алертменеджер, silence

## Сервисы организации

- payments: payments-api, платежи
