import SwiftUI

struct LevelSelectView: View {
    @EnvironmentObject var store: SessionStore

    private let levels: [(level: Int, title: String, subtitle: String)] = [
        (1, "Лёгкий флирт", "Тёплые вопросы для начала"),
        (2, "Личная близость", "Чуть откровеннее, всё ещё легко"),
        (3, "Открытые желания", "Честный разговор о предпочтениях"),
        (4, "Смелые фантазии", "Роли, контроль, доверие"),
        (5, "Горячие темы", "Прямые вопросы без стеснения"),
        (6, "Экспериментальные сценарии", "Темы, которые стоит обсуждать не спеша")
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text("Выберите уровень")
                    .font(.largeTitle.bold())
                    .foregroundStyle(Theme.textPrimary)

                Text("Начните легко и поднимайтесь только тогда, когда обоим комфортно. Уровень можно сменить в любой момент — из паузы.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.textPrimary.opacity(0.7))

                modeRow

                VStack(spacing: 12) {
                    ForEach(levels, id: \.level) { entry in
                        Button {
                            store.selectLevel(entry.level)
                        } label: {
                            HStack {
                                Circle()
                                    .fill(Theme.levelGradient(for: entry.level))
                                    .frame(width: 36, height: 36)
                                    .overlay(Text("\(entry.level)").font(.headline).foregroundStyle(.white))

                                VStack(alignment: .leading, spacing: 2) {
                                    Text(entry.title).font(.headline).foregroundStyle(Theme.textPrimary)
                                    Text(entry.subtitle).font(.caption).foregroundStyle(Theme.textPrimary.opacity(0.6))
                                }

                                Spacer()

                                Image(systemName: "chevron.right")
                                    .foregroundStyle(Theme.textPrimary.opacity(0.4))
                            }
                            .padding(16)
                            .background(Theme.backgroundCard)
                            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(28)
            .frame(maxWidth: 640)
            .frame(maxWidth: .infinity)
        }
    }

    private var modeRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(GameMode.allCases) { mode in
                    Text(mode.title)
                        .font(.caption.bold())
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(mode.isAvailableInM1 ? AnyShapeStyle(Theme.accentPrimary) : AnyShapeStyle(Color.white.opacity(0.08)))
                        .foregroundStyle(mode.isAvailableInM1 ? .white : Theme.textPrimary.opacity(0.4))
                        .clipShape(Capsule())
                }
            }
        }
        .accessibilityLabel("Режим: \(GameMode.questions.title), остальные режимы скоро")
    }
}
