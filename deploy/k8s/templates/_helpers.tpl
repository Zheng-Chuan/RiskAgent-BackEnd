{{/*
Common labels
*/}}
{{- define "riskmonitor.labels" -}}
app.kubernetes.io/name: riskmonitor
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: riskmonitor
{{- end -}}

{{/*
Namespace selector
*/}}
{{- define "riskmonitor.namespace" -}}
namespace: {{ .Release.Namespace | default "riskmonitor" }}
{{- end -}}
