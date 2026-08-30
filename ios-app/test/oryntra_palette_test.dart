import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:oryntra_ai/widgets/common.dart';
import 'package:oryntra_ai/widgets/glass.dart';

void main() {
  test('institutional palette keeps a dark readable surface system', () {
    expect(OryntraPalette.navy.computeLuminance(), lessThan(.02));
    expect(OryntraPalette.ink.computeLuminance(), greaterThan(.8));
    expect(OryntraPalette.blueBright.computeLuminance(), greaterThan(.4));
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
