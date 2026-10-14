# Regras do PSScriptAnalyzer para os scripts do modo nativo (DT-025).
# Write-Host e intencional: os scripts falam com uma pessoa no console.
@{
    Severity     = @('Error', 'Warning')
    ExcludeRules = @('PSAvoidUsingWriteHost')
}
