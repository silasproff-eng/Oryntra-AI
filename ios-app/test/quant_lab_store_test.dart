import 'package:flutter_test/flutter_test.dart';
import 'package:oryntra_ai/services/quant_lab_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('stores, replaces, and deletes local Quant Lab reports', () async {
    SharedPreferences.setMockInitialValues({});
    final store = QuantLabStore();
    final report = <String, dynamic>{
      'dataset_fingerprint': 'fingerprint-one',
      'configuration': {'model': 'v1_corporate_quant_system'},
      'portfolio_risk': {'latest_gross_exposure': 0.8},
    };

    await store.save(report: report, tickers: const ['SPY', 'QQQ', 'IWM']);
    await store.save(report: report, tickers: const ['SPY', 'QQQ', 'IWM']);
    final saved = await store.readAll();

    expect(saved, hasLength(1));
    expect(saved.single['tickers'], ['SPY', 'QQQ', 'IWM']);
    expect(saved.single['report']['dataset_fingerprint'], 'fingerprint-one');

    final remaining = await store.delete('fingerprint-one');
    expect(remaining, isEmpty);
  });
}
