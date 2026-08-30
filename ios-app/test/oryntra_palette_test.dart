import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:oryntra_ai/app_config.dart';
import 'package:oryntra_ai/widgets/common.dart';
import 'package:oryntra_ai/widgets/glass.dart';

void main() {
  test('institutional palette keeps a dark readable surface system', () {
    expect(OryntraPalette.navy.computeLuminance(), lessThan(.02));
    expect(OryntraPalette.ink.computeLuminance(), greaterThan(.8));
    expect(OryntraPalette.blueBright.computeLuminance(), greaterThan(.4));
  });

  test('account traffic defaults to the main Oryntra domain', () {
    expect(AppConfig.authBaseUrl, 'https://oryntraai.com');
    expect(AppConfig.apiBaseUrl, 'https://api.oryntraai.com');
  });

  testWidgets('section labels retain institutional hierarchy', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: InstitutionalSectionLabel(label: 'Market intelligence'),
        ),
      ),
    );

    expect(find.text('MARKET INTELLIGENCE'), findsOneWidget);
  });
}
