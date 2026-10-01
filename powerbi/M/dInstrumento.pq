// dInstrumento: carrega powerbi/dados_modelo/dInstrumento.csv (3 linhas)
// Colar em: Transformar dados > Nova Fonte > Consulta em branco > Editor Avancado
let
    Fonte = Csv.Document(
        File.Contents(pCaminhoDados & "\dInstrumento.csv"),
        [Delimiter = ",", Columns = 1, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Cabecalho = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    // cultura en-US: o CSV usa ponto decimal e datas ISO (AAAA-MM-DD)
    Tipos = Table.TransformColumnTypes(
        Cabecalho,
        {
        {"instrumento_ph", type text}
        },
        "en-US"
    )
in
    Tipos
