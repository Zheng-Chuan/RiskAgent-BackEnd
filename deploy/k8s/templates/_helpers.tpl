{{/*
Common labels
*/}}
{{- define "riskagent.labels" -}}
app.kubernetes.io/name: riskagent
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: riskagent
{{- end -}}

{{/*
Namespace selector
*/}}
{{- define "riskagent.namespace" -}}
namespace: {{ .Release.Namespace | default "riskagent" }}
{{- end -}}
