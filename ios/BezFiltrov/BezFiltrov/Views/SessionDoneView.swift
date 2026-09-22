import SwiftUI

struct SessionDoneView: View {
    @EnvironmentObject var store: SessionStore

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "sparkles")
                .font(.system(size: 56))
                .foregroundStyle(Theme.accentSecondary)

            Text("Спасибо, что были честны друг с другом")
                .font(.title.bold())
                .foregroundStyle(Theme.textPrimary)
                .multilineTextAlignment(.center)

            Text("Ответы aftercare не покидают это устройство и никому не показываются автоматически.")
                .font(.subheadline)
                .foregroundStyle(Theme.textPrimary.opacity(0.6))
                .multilineTextAlignment(.center)

            Button {
                store.startNewSession()
            } label: {
                Text("Новая сессия")
                    .font(.headline)
                    .padding(.horizontal, 24)
                    .padding(.vertical, 10)
            }
            .buttonStyle(.borderedProminent)
            .tint(Theme.accentPrimary)
        }
        .padding(40)
        .frame(maxWidth: 520)
    }
}
