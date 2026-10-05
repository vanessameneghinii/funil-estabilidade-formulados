// dCondicao: carrega powerbi/dados_modelo/dCondicao.csv (6 linhas)
// Colar em: Transformar dados > Nova Fonte > Consulta em branco > Editor Avancado
let
    Fonte = Csv.Document(
        File.Contents(pCaminhoDados & "\dCondicao.csv"),
        [Delimiter = ",", Columns = 6, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Cabecalho = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    // cultura en-US: o CSV usa ponto decimal e datas ISO (AAAA-MM-DD)
    Tipos = Table.TransformColumnTypes(
        Cabecalho,
        {
        {"condicao", type text},
        {"estagio", Int64.Type},
        {"estagio_nome", type text},
        {"ordem", Int64.Type},
        {"exposicao_luz", type logical},
        {"ocupa_camara", type logical}
        },
        "en-US"
    )
in
    Tipos
