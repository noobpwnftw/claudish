// Register, enable, and select an input method bundle through Text Input Sources (Carbon).
// Usage: swift input_source.swift /path/to/Claudish.app org.claudish.inputmethod.Claudish
//        swift input_source.swift --current
import Carbon
import Foundation

func property(_ source: TISInputSource, _ key: CFString) -> String {
    guard let raw = TISGetInputSourceProperty(source, key) else { return "?" }
    return Unmanaged<CFString>.fromOpaque(raw).takeUnretainedValue() as String
}

func flag(_ source: TISInputSource, _ key: CFString) -> Bool {
    guard let raw = TISGetInputSourceProperty(source, key) else { return false }
    return CFBooleanGetValue(Unmanaged<CFBoolean>.fromOpaque(raw).takeUnretainedValue())
}

func current() -> String {
    property(TISCopyCurrentKeyboardInputSource().takeRetainedValue(), kTISPropertyInputSourceID)
}

let args = CommandLine.arguments
if args.count > 1 && args[1] == "--current" {
    print(current())
    exit(0)
}
print("register:", TISRegisterInputSource(URL(fileURLWithPath: args[1]) as CFURL))
let filter = [kTISPropertyBundleID as String: args[2]] as CFDictionary
// A newly registered input method can take a moment before the system lets it be selected.
for attempt in 1...20 {
    let sources = (TISCreateInputSourceList(filter, true)?.takeRetainedValue() as? [TISInputSource]) ?? []
    for source in sources {
        if !flag(source, kTISPropertyInputSourceIsEnabled) {
            print("enable", property(source, kTISPropertyInputSourceID), TISEnableInputSource(source))
        }
    }
    for source in sources where flag(source, kTISPropertyInputSourceIsSelectCapable) {
        let status = TISSelectInputSource(source)
        print("attempt", attempt, "select", property(source, kTISPropertyInputSourceID), status)
        if status == noErr && current().hasPrefix(args[2]) {
            print("current:", current())
            exit(0)
        }
    }
    if attempt == 1 || attempt == 20 {
        for source in sources {
            print("  ", property(source, kTISPropertyInputSourceID),
                  "enabled:", flag(source, kTISPropertyInputSourceIsEnabled),
                  "select-capable:", flag(source, kTISPropertyInputSourceIsSelectCapable))
        }
    }
    Thread.sleep(forTimeInterval: 1)
}
print("current:", current())
exit(1)
