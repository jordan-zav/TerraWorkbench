"""Generate public manual figures from architecture and artificial arrays only.

Requires the documentation extra (Matplotlib). Uses no private survey and no
image-generation service. The numerical figures declare their limited scope.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def asset_sha256(path):
    """Hash SVG as LF text and PNG as exact bytes, consistently across hosts."""
    path = Path(path)
    raw = path.read_bytes()
    if path.suffix.lower() == ".svg":
        raw = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


LABELS = {
    "Una implementación científica, varios puntos de entrada": (
        "One scientific implementation, multiple entry points",
        "Uma implementação científica, vários pontos de entrada",
    ),
    "Datos y contexto": ("Data and context", "Dados e contexto"),
    "Canales, raster, arrays": ("Channels, rasters, arrays", "Canais, raster, arrays"),
    "CRS, unidades, alturas": ("CRS, units, heights", "SRC, unidades, alturas"),
    "Originales conservados": ("Originals preserved", "Originais preservados"),
    "Core científico": ("Scientific Core", "Core científico"),
    "Kernels Python": ("Python kernels", "Kernels Python"),
    "Motores opcionales": ("Optional engines", "Motores opcionais"),
    "Sin QGIS ni Qt": ("No QGIS or Qt", "Sem QGIS ou Qt"),
    "Ejecución": ("Execution", "Execução"),
    "API, jobs y workflows": ("API, jobs, workflows", "API, jobs e workflows"),
    "Recetas y presupuestos": ("Recipes and budgets", "Receitas e orçamentos"),
    "Estados y procedencia": ("Status and provenance", "Estados e procedência"),
    "Interfaz QGIS": ("QGIS interface", "Interface QGIS"),
    "Capas y formularios": ("Layers and forms", "Camadas e formulários"),
    "Explorador y filtros": ("Explorer and filters", "Explorador e filtros"),
    "Vista de resultados": ("Result views", "Visualização de resultados"),
    "Artefactos verificables": ("Verifiable artefacts", "Artefatos verificáveis"),
    "Esquema conceptual del manual; sin datos de campo.": (
        "Conceptual manual diagram; no field data.",
        "Esquema conceitual do manual; sem dados de campo.",
    ),
    "El linaje conserva contenido y receta, además del nombre": (
        "Lineage records content and recipe, not just names",
        "A linhagem conserva conteúdo e receita, além do nome",
    ),
    "field_nt · versión 1": ("field_nt · version 1", "field_nt · versão 1"),
    "base_nt · versión 1": ("base_nt · version 1", "base_nt · versão 1"),
    "anomaly_nt · versión 1": ("anomaly_nt · version 1", "anomaly_nt · versão 1"),
    "lowpass_nt · versión 1": ("lowpass_nt · version 1", "lowpass_nt · versão 1"),
    "Fuente importada": ("Imported source", "Fonte importada"),
    "Unidad y contenido original": (
        "Unit and original content",
        "Unidade e conteúdo original",
    ),
    "Otra observación alineada": (
        "Another aligned observation",
        "Outra observação alinhada",
    ),
    "Soporte temporal verificado": (
        "Verified time support",
        "Suporte temporal verificado",
    ),
    "Entradas por ID de versión": ("Inputs by version ID", "Entradas por ID de versão"),
    "Corte y dominio explícitos": (
        "Explicit cutoff and domain",
        "Corte e domínio explícitos",
    ),
    "Conserva el canal anterior": (
        "Retains the source channel",
        "Conserva o canal anterior",
    ),
    "Original artificial": ("Artificial original", "Original artificial"),
    "Continuada 50 m": ("Continued 50 m", "Continuada 50 m"),
    "Distancia (m)": ("Distance (m)", "Distância (m)"),
    "Amplitud arbitraria": ("Arbitrary amplitude", "Amplitude arbitrária"),
    "Dos longitudes de onda: 640 y 160 m": (
        "Two wavelengths: 640 and 160 m",
        "Dois comprimentos de onda: 640 e 160 m",
    ),
    "Modos medidos tras FFT": ("Measured FFT modes", "Modos medidos após FFT"),
    "Número de onda angular (rad/m)": (
        "Angular wavenumber (rad/m)",
        "Número de onda angular (rad/m)",
    ),
    "Ganancia": ("Gain", "Ganho"),
    "Atenuación con h = 50 m": ("Attenuation at h = 50 m", "Atenuação com h = 50 m"),
    "Modelo A": ("Model A", "Modelo A"),
    "Modelo B": ("Model B", "Modelo B"),
    "Propiedad arbitraria": ("Arbitrary property", "Propriedade arbitrária"),
    "Modelos distintos": ("Different models", "Modelos distintos"),
    "Observación": ("Observation", "Observação"),
    "Respuesta arbitraria": ("Arbitrary response", "Resposta arbitrária"),
    "Datos idénticos": ("Identical data", "Dados idênticos"),
}


def translated(text, locale):
    if locale == "es" or text not in LABELS:
        return text
    return LABELS[text][("en", "pt").index(locale)]


def localize_figure(figure, locale):
    from matplotlib.text import Text

    for artist in figure.findobj(match=Text):
        artist.set_text(translated(artist.get_text(), locale))


def diagram(path, boxes, edges, title, locale="es"):
    title = translated(title, locale)
    boxes = [
        (
            x,
            y,
            w,
            h,
            translated(heading, locale),
            [translated(line, locale) for line in lines],
        )
        for x, y, w, h, heading, lines in boxes
    ]
    from html import escape

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="430" viewBox="0 0 1120 430">',
        '<rect width="1120" height="430" fill="white"/>',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8" fill="#31556c"/></marker></defs>',
        '<g font-family="Arial, sans-serif" fill="#17394c">',
        '<text x="35" y="40" font-size="23" font-weight="bold">'
        + escape(title)
        + "</text>",
    ]
    for x1, y1, x2, y2 in edges:
        parts.append(
            f'<path d="M{x1},{y1} L{x2},{y2}" stroke="#31556c" stroke-width="2.5" fill="none" marker-end="url(#arrow)"/>'
        )
    for x, y, w, h, heading, lines in boxes:
        parts += [
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#eef5f8" stroke="#7194a8"/>',
            f'<text x="{x + 14}" y="{y + 30}" font-size="18" font-weight="bold">{escape(heading)}</text>',
        ]
        for index, line in enumerate(lines):
            parts.append(
                f'<text x="{x + 14}" y="{y + 60 + index * 23}" font-size="16">{escape(line)}</text>'
            )
    parts += [
        '<text x="35" y="407" font-size="15">'
        + escape(
            translated("Esquema conceptual del manual; sin datos de campo.", locale)
        )
        + "</text>",
        "</g></svg>",
    ]
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def compact_architecture(output, locale):
    """Reflow the same architecture into vertical cards without shrinking its labels."""
    from html import escape
    cards = [
        ("Datos y contexto", ["Canales, raster, arrays", "CRS, unidades, alturas", "Originales conservados"]),
        ("Core científico", ["Kernels Python", "Motores opcionales", "Sin QGIS ni Qt"]),
        ("Ejecución", ["API, jobs y workflows", "Recetas y presupuestos", "Estados y procedencia"]),
        ("Interfaz QGIS", ["Capas y formularios", "Explorador y filtros", "Vista de resultados"]),
        ("Artefactos verificables", ["Parquet · GeoTIFF · CSV · JSON · NPZ · VTK"]),
    ]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="680" height="1050" viewBox="0 0 680 1050">',
             '<rect width="680" height="1050" fill="white"/>',
             '<defs><marker id="a" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8" fill="#31556c"/></marker></defs>',
             '<g font-family="Arial, sans-serif" fill="#17394c">',
             '<text x="20" y="38" font-size="20" font-weight="bold">' + escape(translated("Una implementación científica, varios puntos de entrada", locale)) + '</text>']
    for index, (heading, lines) in enumerate(cards):
        y = 80 + index * 190
        parts.append(f'<rect x="20" y="{y}" width="600" height="150" rx="8" fill="#eef5f8" stroke="#7194a8"/>')
        parts.append(f'<text x="40" y="{y+32}" font-size="18" font-weight="bold">{escape(translated(heading, locale))}</text>')
        for number, line in enumerate(lines):
            parts.append(f'<text x="40" y="{y+65+number*23}" font-size="16">{escape(translated(line, locale))}</text>')
        if index < 3:
            parts.append(f'<path d="M320,{y+150} L320,{y+185}" stroke="#31556c" stroke-width="2.5" marker-end="url(#a)"/>')
    parts.append('<path d="M620,530 L650,530 L650,910 L625,910" stroke="#31556c" stroke-width="2.5" fill="none" marker-end="url(#a)"/>')
    parts.append('<text x="20" y="1030" font-size="15">'+escape(translated("Esquema conceptual del manual; sin datos de campo.",locale))+'</text></g></svg>')
    (Path(output) / "arquitectura_compacta.svg").write_text("\n".join(parts)+"\n", encoding="utf-8")


def build(output, locale="es"):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from examples.manual.fft import synthetic_case

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    diagram(
        output / "arquitectura.svg",
        [
            (
                35,
                90,
                235,
                155,
                "Datos y contexto",
                [
                    "Canales, raster, arrays",
                    "CRS, unidades, alturas",
                    "Originales conservados",
                ],
            ),
            (
                305,
                90,
                235,
                155,
                "Core científico",
                ["Kernels Python", "Motores opcionales", "Sin QGIS ni Qt"],
            ),
            (
                575,
                90,
                235,
                155,
                "Ejecución",
                [
                    "API, jobs y workflows",
                    "Recetas y presupuestos",
                    "Estados y procedencia",
                ],
            ),
            (
                845,
                90,
                235,
                155,
                "Interfaz QGIS",
                ["Capas y formularios", "Explorador y filtros", "Vista de resultados"],
            ),
            (
                305,
                285,
                505,
                85,
                "Artefactos verificables",
                ["Parquet · GeoTIFF · CSV · JSON · NPZ · VTK"],
            ),
        ],
        [
            (270, 165, 300, 165),
            (540, 165, 570, 165),
            (810, 165, 840, 165),
            (690, 245, 690, 280),
        ],
        "Una implementación científica, varios puntos de entrada",
        locale,
    )
    compact_architecture(output, locale)
    diagram(
        output / "linaje.svg",
        [
            (
                45,
                95,
                280,
                110,
                "field_nt · versión 1",
                ["Fuente importada", "Unidad y contenido original"],
            ),
            (
                45,
                245,
                280,
                110,
                "base_nt · versión 1",
                ["Otra observación alineada", "Soporte temporal verificado"],
            ),
            (
                405,
                170,
                280,
                120,
                "anomaly_nt · versión 1",
                ["field_nt − base_nt", "Entradas por ID de versión"],
            ),
            (
                765,
                170,
                300,
                120,
                "lowpass_nt · versión 1",
                ["Corte y dominio explícitos", "Conserva el canal anterior"],
            ),
        ],
        [(325, 150, 400, 205), (325, 300, 400, 235), (685, 230, 760, 230)],
        "El linaje conserva contenido y receta, además del nombre",
        locale,
    )
    plt.rcParams.update(
        {"font.size": 11, "axes.spines.top": False, "axes.spines.right": False}
    )
    x, original, continued, expected, metrics = synthetic_case()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), layout="constrained")
    axes[0].plot(x, original[0], label="Original artificial", lw=1.3)
    axes[0].plot(x, continued[0], label="Continuada 50 m", lw=1.5)
    axes[0].set(
        xlim=(0, 1280),
        xlabel="Distancia (m)",
        ylabel="Amplitud arbitraria",
        title="Dos longitudes de onda: 640 y 160 m",
    )
    axes[0].legend(fontsize=9)
    k = np.linspace(0, 0.06, 300)
    axes[1].plot(k, np.exp(-50 * k), label="exp(−k h)")
    ks = 2 * np.pi / np.array([640.0, 160.0])
    bins = np.array([4, 16])
    measured = np.abs(np.fft.rfft(continued[0])[bins]) / np.abs(
        np.fft.rfft(original[0])[bins]
    )
    np.testing.assert_allclose(measured, np.exp(-50 * ks), atol=1e-12)
    axes[1].scatter(ks, measured, color="#b04b32", label="Modos medidos tras FFT")
    axes[1].set(
        xlabel="Número de onda angular (rad/m)",
        ylabel="Ganancia",
        title="Atenuación con h = 50 m",
    )
    axes[1].legend(fontsize=9)
    localize_figure(fig, locale)
    fig.savefig(
        output / "continuacion.png",
        dpi=160,
        metadata={"Description": "Artificial periodic signal; not field validation"},
    )
    plt.close(fig)
    # A declared underdetermined linear model with an explicit null vector.
    sensitivity = np.array([[1.0, 1.0, 0.0], [0.0, 1.0, 1.0]])
    a = np.array([1.0, 2.0, 3.0])
    b = a + np.array([1.0, -1.0, 1.0]) * 1.5
    np.testing.assert_allclose(sensitivity @ a, sensitivity @ b, atol=1e-14)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
    positions = np.arange(3)
    axes[0].bar(positions - 0.16, a, width=0.3, label="Modelo A")
    axes[0].bar(positions + 0.16, b, width=0.3, label="Modelo B")
    axes[0].set(
        xticks=positions,
        xticklabels=["m₁", "m₂", "m₃"],
        ylabel="Propiedad arbitraria",
        title="Modelos distintos",
    )
    axes[0].legend()
    axes[1].plot([1, 2], sensitivity @ a, "o", ms=12, label="G · A")
    axes[1].plot([1, 2], sensitivity @ b, "x", ms=10, label="G · B")
    axes[1].set(
        xticks=[1, 2],
        xlabel="Observación",
        ylabel="Respuesta arbitraria",
        title="Datos idénticos",
    )
    axes[1].legend()
    localize_figure(fig, locale)
    fig.savefig(
        output / "no_unicidad.png",
        dpi=160,
        metadata={
            "Description": "Declared linear null-space example; not a geophysical benchmark"
        },
    )
    plt.close(fig)
    manifest = {
        "scope": "conceptual diagrams and controlled numerical figures; real-data captures have a separate manifest",
        "locale": locale,
        "fft": metrics,
        "linear_null_error": float(np.max(abs(sensitivity @ a - sensitivity @ b))),
        "hash_scheme": "sha256: SVG text normalized to LF; PNG exact bytes",
        "files": {
            p.name: asset_sha256(p)
            for p in sorted(output.iterdir())
            if p.suffix in (".svg", ".png")
            and p.stem in ("arquitectura", "arquitectura_compacta", "linaje", "continuacion", "no_unicidad")
        },
    }
    (output / "figuras.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--locale", choices=("es", "en", "pt"), default="es")
    args = parser.parse_args()
    output = args.output or ROOT / "docs/manuals/assets" / args.locale
    print(json.dumps(build(output, args.locale), indent=2))
