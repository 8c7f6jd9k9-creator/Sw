import SwiftUI

/// "Точно да / возможно / точно нет / обсудить позже" — reused on the
/// consent screen and (v1.1+) in-session boundary review.
struct BoundaryPicker: View {
    let title: String
    @Binding var level: BoundaryLevel

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.subheadline)
                .foregroundStyle(Theme.textPrimary.opacity(0.85))

            Picker(title, selection: $level) {
                ForEach(BoundaryLevel.allCases) { option in
                    Text(option.title).tag(option)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
        }
        .padding(.vertical, 4)
    }
}
