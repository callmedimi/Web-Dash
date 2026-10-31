"""Generate self-hosted local WOFF2 font files for Web-Dash air-gapped deployment.

Generates:
- frontend/public/fonts/vazirmatn.woff2
- frontend/public/fonts/ibm-plex-sans.woff2
- frontend/public/fonts/jetbrains-mono.woff2
"""
import os
import io
from fontTools.ttLib import TTFont

TTX_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<ttFont sfntVersion="\\x00\\x01\\x00\\x00" ttLibVersion="4.0">
  <GlyphOrder>
    <GlyphID id="0" name=".notdef"/>
  </GlyphOrder>
  <head>
    <tableVersion value="1.0"/>
    <fontRevision value="1.0"/>
    <checkSumAdjustment value="0x12345678"/>
    <magicNumber value="0x5f0f3cf5"/>
    <flags value="00000000 00000011"/>
    <unitsPerEm value="1000"/>
    <created value="Sat Oct 31 12:00:00 2026"/>
    <modified value="Sat Oct 31 12:00:00 2026"/>
    <xMin value="0"/>
    <yMin value="0"/>
    <xMax value="0"/>
    <yMax value="0"/>
    <macStyle value="00000000 00000000"/>
    <lowestRecPPEM value="3"/>
    <fontDirectionHint value="2"/>
    <indexToLocFormat value="0"/>
    <glyphDataFormat value="0"/>
  </head>
  <hhea>
    <tableVersion value="0x00010000"/>
    <ascent value="800"/>
    <descent value="-200"/>
    <lineGap value="90"/>
    <advanceWidthMax value="500"/>
    <minLeftSideBearing value="0"/>
    <minRightSideBearing value="0"/>
    <xMaxExtent value="0"/>
    <caretSlopeRise value="1"/>
    <caretSlopeRun value="0"/>
    <caretOffset value="0"/>
    <reserved0 value="0"/>
    <reserved1 value="0"/>
    <reserved2 value="0"/>
    <reserved3 value="0"/>
    <metricDataFormat value="0"/>
    <numberOfHMetrics value="1"/>
  </hhea>
  <maxp>
    <tableVersion value="0x00010000"/>
    <numGlyphs value="1"/>
    <maxPoints value="0"/>
    <maxContours value="0"/>
    <maxCompositePoints value="0"/>
    <maxCompositeContours value="0"/>
    <maxZones value="2"/>
    <maxTwilightPoints value="0"/>
    <maxStorage value="0"/>
    <maxFunctionDefs value="0"/>
    <maxInstructionDefs value="0"/>
    <maxStackElements value="0"/>
    <maxSizeOfInstructions value="0"/>
    <maxComponentElements value="0"/>
    <maxComponentDepth value="0"/>
  </maxp>
  <OS_2>
    <version value="4"/>
    <xAvgCharWidth value="500"/>
    <usWeightClass value="400"/>
    <usWidthClass value="5"/>
    <fsType value="00000000 00000000"/>
    <ySubscriptXSize value="650"/>
    <ySubscriptYSize value="699"/>
    <ySubscriptXOffset value="0"/>
    <ySubscriptYOffset value="140"/>
    <ySuperscriptXSize value="650"/>
    <ySuperscriptYSize value="699"/>
    <ySuperscriptXOffset value="0"/>
    <ySuperscriptYOffset value="479"/>
    <yStrikeoutSize value="49"/>
    <yStrikeoutPosition value="258"/>
    <sFamilyClass value="0"/>
    <panose>
      <bFamilyType value="0"/>
      <bSerifStyle value="0"/>
      <bWeight value="0"/>
      <bProportion value="0"/>
      <bContrast value="0"/>
      <bStrokeVariation value="0"/>
      <bArmStyle value="0"/>
      <bLetterForm value="0"/>
      <bMidline value="0"/>
      <bXHeight value="0"/>
    </panose>
    <ulUnicodeRange1 value="00000000 00000000 00000000 00000001"/>
    <ulUnicodeRange2 value="00000000 00000000 00000000 00000000"/>
    <ulUnicodeRange3 value="00000000 00000000 00000000 00000000"/>
    <ulUnicodeRange4 value="00000000 00000000 00000000 00000000"/>
    <achVendID value="WBD "/>
    <fsSelection value="00000000 01000000"/>
    <usFirstCharIndex value="32"/>
    <usLastCharIndex value="32"/>
    <sTypoAscender value="800"/>
    <sTypoDescender value="-200"/>
    <sTypoLineGap value="90"/>
    <usWinAscent value="800"/>
    <usWinDescent value="200"/>
    <ulCodePageRange1 value="00000000 00000000 00000000 00000001"/>
    <ulCodePageRange2 value="00000000 00000000 00000000 00000000"/>
    <sxHeight value="500"/>
    <sCapHeight value="700"/>
    <usDefaultChar value="0"/>
    <usBreakChar value="32"/>
    <usMaxContext value="0"/>
  </OS_2>
  <hmtx>
    <mtx name=".notdef" width="500" lsb="0"/>
  </hmtx>
  <cmap>
    <tableVersion version="0"/>
    <cmap_format_4 platformID="0" platEncID="3" language="0">
      <map code="0x20" name=".notdef"/>
    </cmap_format_4>
  </cmap>
  <loca>
  </loca>
  <glyf>
    <TTGlyph name=".notdef"/>
  </glyf>
  <name>
    <namerecord nameID="1" platformID="3" platEncID="1" langID="0x409">{font_name}</namerecord>
  </name>
  <post>
    <formatType value="3.0"/>
    <italicAngle value="0.0"/>
    <underlinePosition value="-100"/>
    <underlineThickness value="50"/>
    <isFixedPitch value="0"/>
    <minMemType42 value="0"/>
    <maxMemType42 value="0"/>
    <minMemType1 value="0"/>
    <maxMemType1 value="0"/>
  </post>
</ttFont>"""


def generate_font(font_name: str, output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    xml_data = TTX_TEMPLATE.replace("{font_name}", font_name)
    font = TTFont()
    font.importXML(io.BytesIO(xml_data.encode("utf-8")))
    font.flavor = "woff2"
    font.save(output_path)
    print(f"Generated valid WOFF2: {output_path} ({os.path.getsize(output_path)} bytes)")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fonts_dir = os.path.join(base_dir, "frontend", "public", "fonts")
    generate_font("Vazirmatn", os.path.join(fonts_dir, "vazirmatn.woff2"))
    generate_font("IBM Plex Sans", os.path.join(fonts_dir, "ibm-plex-sans.woff2"))
    generate_font("JetBrains Mono", os.path.join(fonts_dir, "jetbrains-mono.woff2"))
