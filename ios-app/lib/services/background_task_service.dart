import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class BackgroundTaskService {
  static const _channel = MethodChannel('oryntra/background_task');

  Future<bool> beginQuantLabRun() async {
    if (kIsWeb) return false;
    try {
      return await _channel.invokeMethod<bool>('beginQuantLabRun') ?? false;
    } on MissingPluginException {
      return false;
    }
  }

  Future<void> endQuantLabRun() async {
    if (kIsWeb) return;
    try {
      await _channel.invokeMethod<void>('endQuantLabRun');
    } on MissingPluginException {
      // Non-iOS platforms do not install the iOS background task channel.
    }
  }
}
