import SwiftUI

struct TurnBadgeView: View {
    @EnvironmentObject var store: GameStore

    private var activeName: String {
        store.isPlayerOneTurn ? store.settings.playerOneName : store.settings.playerTwoName
    }

    var body: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(LevelTheme.gradient(for: store.selectedLevelID))
                .frame(width: 34, height: 34)
                .overlay(
                    Text(String(activeName.prefix(1)).uppercased())
                        .font(.headline)
                        .foregroundStyle(.white)
                )

            Text("Отвечает: \(activeName)")
                .font(.subheadline.bold())

            Spacer()

            Button {
                store.isPlayerOneTurn.toggle()
            } label: {
                Label("Поменяться", systemImage: "arrow.left.arrow.right")
                    .font(.caption)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding(12)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}
