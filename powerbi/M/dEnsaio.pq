// dEnsaio: carrega powerbi/dados_modelo/dEnsaio.csv (11 linhas)
// Colar em: Transformar dados > Nova Fonte > Consulta em branco > Editor Avancado
let
    Fonte = Csv.Document(
        File.Contents(pCaminhoDados & "\dEnsaio.csv"),
        [Delimiter = ",", Columns = 5, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Cabecalho = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    // cultura en-US: o CSV usa ponto decimal e datas ISO (AAAA-MM-DD)
    Tipos = Table.TransformColumnTypes(
        Cabecalho,
        {
        {"ensaio", type text},
        {"grupo", type text},
        {"tipo_valor", type text},
        {"unidade", type text},
        {"ordem", Int64.Type}
        },
        "en-US"
    )
in
    Tipos
