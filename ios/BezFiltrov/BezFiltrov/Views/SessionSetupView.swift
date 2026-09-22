import SwiftUI

struct SessionSetupView: View {
    @EnvironmentObject var store: SessionStore

    @State private var kind: SessionKind = .pair
    @State private var deviceMode: DeviceMode = .passDevice
    @State private var relationshipFormat: RelationshipFormat = .any

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                Text("Создание сессии")
                    .font(.largeTitle.bold())
                    .foregroundStyle(Theme.textPrimary)

                sectionCard(title: "Кто играет") {
                    Picker("", selection: $kind) {
                        Text("Пара").tag(SessionKind.pair)
                        Text("Группа").tag(SessionKind.group)
                    }
                    .pickerStyle(.segmented)
                }

                sectionCard(title: "Устройство") {
                    Picker("", selection: $deviceMode) {
                        Text("Один iPad, передаём по кругу").tag(DeviceMode.passDevice)
                        Text("У каждого своё устройство").tag(DeviceMode.singleShared)
                    }
                    .pickerStyle(.segmented)

                    Text("«Передай планшет» скрывает приватные ответы от того, у кого сейчас устройство в руках.")
                        .font(.caption)
                        .foregroundStyle(Theme.textPrimary.opacity(0.6))
                }

                sectionCard(title: "Формат (необязательно)") {
                    Text("Готовые фильтры — не ярлык на вас, а способ приложению показывать только релевантные карточки.")
                        .font(.caption)
                        .foregroundStyle(Theme.textPrimary.opacity(0.6))

                    Picker("Формат", selection: $relationshipFormat) {
                        ForEach(RelationshipFormat.allCases) { format in
                            Text(format.title).tag(format)
                        }
                    }
                    .pickerStyle(.menu)
                    .tint(Theme.accentSecondary)
                }

                Button {
                    store.startSetup(kind: kind, deviceMode: deviceMode, relationshipFormat: relationshipFormat)
                } label: {
                    Text("Дальше: игроки")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.accentPrimary)
                .controlSize(.large)
            }
            .padding(28)
            .frame(maxWidth: 640)
            .frame(maxWidth: .infinity)
        }
    }

    private func sectionCard<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.headline)
                .foregroundStyle(Theme.textPrimary)
            content()
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.backgroundCard)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}
