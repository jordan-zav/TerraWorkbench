# 20. FDEM, TEM, transientes e magnetotelúrica

[English](../en/20_em_mt.md) · [Español](../es/20_em_mt.md) · [Português](../pt/20_em_mt.md)

## Separar os problemas

FDEM usa frequências discretas e resposta complexa; TEM usa evolução temporal, excitação e janelas. MT usa impedância de campos naturais com convenções próprias de eixos/unidades. Condutividade ajustada depende de geometria, calibração e parametrização em todos esses modelos.

## FDEM

fdem_layered representa Terra estratificada e fit_fdem_conductivity ajusta condutividades com geometria fixa. Registrar separação, orientação e altura de transmissor/receptor, frequência, momento e componente. Não trocar B secundária em teslas por ppm do primário sem conversão instrumental apropriada.

fdem_3d_forward e fit_fdem_3d_zones fornecem campos 3D isotrópicos e ajuste local por zonas em malha explícita. A fatoração esparsa impõe limites de trabalho. Isso não estabelece inversão industrial de milhões de voxels, anisotropia ou projeto automático de malha.

complex_calibration ajusta/aplica resposta complexa. Calibração de amplitude/fase exige padrões e contexto instrumental; informação de transferência ausente não justifica supor resposta unitária.

## TEM e janelas

tem_stepoff_layered modela desligamento ideal; tem_waveform_layered incorpora forma de onda linear por trechos. Informar se a variável é B ou dB/dt e suas unidades; os contratos usam T/s para dB/dt quando pertinente. Dipolo ideal não equivale a espira finita com eletrônica real.

tem_gate_average, stack_transients e gate_recorded_transients distinguem previsão integrada, dados registrados e empilhamento. Definir tempos absolutos ou relativos ao desligamento, larguras e sinais dos pulsos. Interpolação não cria suporte fora do registro.

## MT

magnetotellurics usa Z = E/H em ohms, convenção exp(+iωt) e eixos Norte/Leste. A resposta 1D tem Zxy positivo e Zyx = −Zxy. Resistividade aparente depende de |Z|²/(μ₀ω); E/B em vez de E/H muda unidades e exige conversão.

layered_impedance, apparent_resistivity_phase, phase_tensor e fit_layered_resistivity fornecem primitivas e ajustes. O módulo não é leitor EDI/MTH5 nem estimador robusto de funções de transferência de séries temporais. Calcular tensor de fase não valida campos de entrada nem elimina toda distorção instrumental.

Ver [métodos e limites](../../research/core_expansion_implementation.md), [validação de inversões](../../validation/reports/inversion_methods_validation.md) e [catálogo SimPEG](https://simpeg.xyz/). Não atribuir ao TerraWorkbench todas as capacidades do motor externo.

## Implementação relacionada

[layered_em](../../../terraworkbench_core/layered_em.py), [fdem_3d](../../../terraworkbench_core/fdem_3d.py), [magnetotellurics](../../../terraworkbench_core/magnetotellurics.py), [transient_processing](../../../terraworkbench_core/transient_processing.py), [complex_calibration](../../../terraworkbench_core/complex_calibration.py)

---

[Índice](README.md) · [Anterior](19_ip_sip.md) · [Próximo](21_potencial_espontaneo.md)
