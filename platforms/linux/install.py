#!/usr/bin/python3
"""Register only: does not enable or replace the user's input methods."""
from pathlib import Path
from xml.sax.saxutils import escape

root = Path(__file__).resolve().parents[2]
destination = Path.home() / ".local/share/ibus/component/claudish.xml"
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text('''<?xml version="1.0" encoding="utf-8"?>
<component>
  <name>org.freedesktop.IBus.Claudish</name>
  <description>Claudish local language model IME</description>
  <exec>/usr/bin/python3 &quot;%s&quot; --ibus</exec>
  <version>0.1.0</version>
  <license>MIT</license>
  <author>Claudish contributors</author>
  <engines><engine>
    <name>claudish</name>
    <longname>cd_AI — Claudish</longname>
    <description>English goes in, em dashes come out</description>
    <language>en</language>
    <license>MIT</license>
    <author>Claudish contributors</author>
    <layout>us</layout>
    <symbol>cd</symbol>
  </engine></engines>
</component>
''' % escape(str(root / "platforms/linux/engine.py")), encoding="utf-8")
print("Registered", destination)
print("Log out/in, then add English → cd_AI — Claudish in Input Sources.")
print("Remove this XML file to unregister. The source folder must stay in place.")
