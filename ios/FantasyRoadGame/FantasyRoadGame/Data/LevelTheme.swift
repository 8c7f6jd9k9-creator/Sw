import SwiftUI

enum LevelTheme {

    static func colors(for levelID: Int) -> [Color] {
        switch levelID {
        case 0: return [Color(hex: "8E9AAF"), Color(hex: "5C6B8A")]
        case 1: return [Color(hex: "FFD6E8"), Color(hex: "FFB6D9")]
        case 2: return [Color(hex: "FFB6C1"), Color(hex: "FF7AA2")]
        case 3: return [Color(hex: "FF8A65"), Color(hex: "FF5252")]
        case 4: return [Color(hex: "E53960"), Color(hex: "B71C4A")]
        case 5: return [Color(hex: "3A0CA3"), Color(hex: "240046")]
        case 6: return [Color(hex: "1B1B2F"), Color(hex: "16161D")]
        default: return [Color.pink, Color.purple]
        }
    }

    static func gradient(for levelID: Int) -> LinearGradient {
        LinearGradient(colors: colors(for: levelID), startPoint: .topLeading, endPoint: .bottomTrailing)
    }
}

extension Color {
    init(hex: String) {
        let scanner = Scanner(string: hex)
        var rgbValue: UInt64 = 0
        scanner.scanHexInt64(&rgbValue)
        let red = Double((rgbValue & 0xFF0000) >> 16) / 255
        let green = Double((rgbValue & 0x00FF00) >> 8) / 255
        let blue = Double(rgbValue & 0x0000FF) / 255
        self.init(red: red, green: green, blue: blue)
    }
}
