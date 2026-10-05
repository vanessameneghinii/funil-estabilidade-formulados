// dCalendario: dimensao de datas GERADA em M com List.Dates (nao importada de arquivo).
// Limites derivados dos dados: 1 de janeiro do primeiro ano a 31 de dezembro do ultimo.
// Dependencia: consulta fMedicoes carregada e tipada antes desta.
// Apos carregar: Modelagem > Marcar como tabela de datas > coluna [Data].
let
    DataMin = Date.StartOfYear(List.Min({List.Min(fMedicoes[data_amostra]), List.Min(fMedicoes[data_inicio_lote])})),
    DataMax = Date.EndOfYear(List.Max(fMedicoes[data_amostra])),
    Datas = List.Dates(DataMin, Duration.Days(DataMax - DataMin) + 1, #duration(1, 0, 0, 0)),
    Tabela = Table.FromList(Datas, Splitter.SplitByNothing(), {"Data"}, null, ExtraValues.Error),
    Tipada = Table.TransformColumnTypes(Tabela, {{"Data", type date}}),
    Ano = Table.AddColumn(Tipada, "Ano", each Date.Year([Data]), Int64.Type),
    MesNum = Table.AddColumn(Ano, "MesNum", each Date.Month([Data]), Int64.Type),
    Mes = Table.AddColumn(MesNum, "Mes", each Text.Proper(Date.ToText([Data], [Format = "MMM", Culture = "pt-BR"])), type text),
    AnoMes = Table.AddColumn(Mes, "AnoMes", each Date.ToText([Data], [Format = "yyyy-MM", Culture = "en-US"]), type text),
    Trimestre = Table.AddColumn(AnoMes, "Trimestre", each "T" & Text.From(Date.QuarterOfYear([Data])), type text),
    DiaSemanaNum = Table.AddColumn(Trimestre, "DiaSemanaNum", each Date.DayOfWeek([Data], Day.Monday) + 1, Int64.Type),
    DiaSemana = Table.AddColumn(DiaSemanaNum, "DiaSemana", each Text.Proper(Date.ToText([Data], [Format = "ddd", Culture = "pt-BR"])), type text),
    FimDeSemana = Table.AddColumn(DiaSemana, "FimDeSemana", each [DiaSemanaNum] >= 6, type logical)
in
    FimDeSemana
