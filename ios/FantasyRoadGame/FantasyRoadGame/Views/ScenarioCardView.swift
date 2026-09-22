import SwiftUI

struct ScenarioCardView: View {
    let scenario: GeneratedScenario?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let scenario {
                row(label: "Где", value: scenario.whereText, icon: "mappin.and.ellipse")
                row(label: "Когда", value: scenario.whenText, icon: "clock")
                row(label: "С кем", value: scenario.withWhomText, icon: "person.2.fill")
                row(label: "Куда", value: scenario.goalText, icon: "arrow.forward.circle")
            } else {
                Text("Нажмите «Сгенерировать», чтобы собрать случайный сценарий вечера.")
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.9))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(28)
        .background(LevelTheme.gradient(for: scenario?.levelID ?? 2))
        .foregroundStyle(.white)
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .shadow(color: .black.opacity(0.18), radius: 16, y: 8)
        .accessibilityElement(children: .combine)
    }

    private func row(label: String, value: String, icon: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon)
                .font(.headline)
                .frame(width: 22)

            VStack(alignment: .leading, spacing: 2) {
                Text(label.uppercased())
                    .font(.caption.bold())
                    .tracking(1.2)
                    .foregroundStyle(.white.opacity(0.75))
                Text(value)
                    .font(.system(size: 18, weight: .semibold, design: .rounded))
            }
        }
    }
}
