// fMedicoes: carrega powerbi/dados_modelo/fMedicoes.csv (29,421 linhas)
// Colar em: Transformar dados > Nova Fonte > Consulta em branco > Editor Avancado
let
    Fonte = Csv.Document(
        File.Contents(pCaminhoDados & "\fMedicoes.csv"),
        [Delimiter = ",", Columns = 16, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Cabecalho = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    // cultura en-US: o CSV usa ponto decimal e datas ISO (AAAA-MM-DD)
    Tipos = Table.TransformColumnTypes(
        Cabecalho,
        {
        {"lote", type text},
        {"condicao", type text},
        {"ensaio", type text},
        {"analista", type text},
        {"instrumento_ph", type text},
        {"data_amostra", type date},
        {"data_inicio_lote", type date},
        {"tempo_dias", Int64.Type},
        {"valor", type number},
        {"limite_min", type number},
        {"limite_max", type number},
        {"versao_spec", type text},
        {"julgavel", type logical},
        {"oos", type logical},
        {"valor_impossivel", type logical},
        {"motivo", type text}
        },
        "en-US"
    )
in
    Tipos
