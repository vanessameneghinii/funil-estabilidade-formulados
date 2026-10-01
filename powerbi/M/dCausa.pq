// dCausa: carrega powerbi/dados_modelo/dCausa.csv (8 linhas)
// Colar em: Transformar dados > Nova Fonte > Consulta em branco > Editor Avancado
let
    Fonte = Csv.Document(
        File.Contents(pCaminhoDados & "\dCausa.csv"),
        [Delimiter = ",", Columns = 3, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Cabecalho = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    // cultura en-US: o CSV usa ponto decimal e datas ISO (AAAA-MM-DD)
    Tipos = Table.TransformColumnTypes(
        Cabecalho,
        {
        {"causa", type text},
        {"grupo_causa", type text},
        {"ordem", Int64.Type}
        },
        "en-US"
    )
in
    Tipos
