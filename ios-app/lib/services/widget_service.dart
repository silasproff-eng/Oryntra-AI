import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class WidgetService {
  static const _channel = MethodChannel('oryntra/widget');

  Future<void> updateScan({
    required String ticker,
    required String signal,
    required String price,
    required String quality,
  }) async {
    if (kIsWeb) return;
    try {
      await _channel.invokeMethod<void>('updateScan', {
        'ticker': ticker,
        'signal': signal,
        'price': price,
        'quality': quality,
        'updatedAt': DateTime.now().toIso8601String(),
      });
    } on MissingPluginException {
      
    }
  }
}
