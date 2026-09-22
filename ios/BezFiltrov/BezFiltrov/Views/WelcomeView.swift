import SwiftUI

struct WelcomeView: View {
    @EnvironmentObject var store: SessionStore
    @State private var ageConfirmed = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Без фильтров")
                        .font(.system(size: 44, weight: .bold, design: .rounded))
                        .foregroundStyle(Theme.textPrimary)

                    Text("Игра-разговор для совершеннолетних о желаниях, границах и согласии.")
                        .font(.title3)
                        .foregroundStyle(Theme.textPrimary.opacity(0.75))
                }

                VStack(alignment: .leading, spacing: 14) {
                    infoRow(icon: "checkmark.seal.fill", text: "Только для взрослых, только по обоюдному желанию.")
                    infoRow(icon: "forward.circle.fill", text: "Любую карточку можно пропустить без объяснений.")
                    infoRow(icon: "hand.raised.fill", text: "Пауза и «Завершить игру» доступны в любой момент.")
                    infoRow(icon: "sparkles", text: "Фантазия не значит обязательство её воплотить.")
                }

                Text("Не играйте в состоянии сильного алкогольного или наркотического опьянения — согласие должно быть осознанным.")
                    .font(.footnote)
                    .foregroundStyle(Theme.textPrimary.opacity(0.6))

                Toggle(isOn: $ageConfirmed) {
                    Text("Мне есть 18 лет, и я подтверждаю это добровольно.")
                        .foregroundStyle(Theme.textPrimary)
                }
                .tint(Theme.accentPrimary)

                Button {
                    store.confirmAgeGate()
                } label: {
                    Text("Начать")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.accentPrimary)
                .controlSize(.large)
                .disabled(!ageConfirmed)
            }
            .padding(28)
            .frame(maxWidth: 640)
            .frame(maxWidth: .infinity)
        }
    }

    private func infoRow(icon: String, text: String) -> some View {
        Label {
            Text(text).foregroundStyle(Theme.textPrimary.opacity(0.85))
        } icon: {
            Image(systemName: icon).foregroundStyle(Theme.accentSecondary)
        }
        .font(.subheadline)
    }
}
