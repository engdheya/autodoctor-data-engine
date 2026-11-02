/// Contract for a future assistant. It may only explain what the database says.
///
/// Every answer must declare whether it came from the bundle or from inference, so the UI
/// can label an inference as such. The assistant never invents causes, values or procedures,
/// and no paid provider is called in this build.
library;

enum AnswerOrigin { database, inference }

class AssistantAnswer {
  const AssistantAnswer({
    required this.origin,
    required this.text,
    required this.citedContextKeys,
  });

  final AnswerOrigin origin;
  final String text;

  /// The codes the answer was built from. Empty for an inference-only answer.
  final List<String> citedContextKeys;
}

abstract class DiagnosisAssistant {
  Future<AssistantAnswer> explain(String contextKey, {required String language});

  Future<AssistantAnswer> ask(String contextKey, String question, {required String language});
}
