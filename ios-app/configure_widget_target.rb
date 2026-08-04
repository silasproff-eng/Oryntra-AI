#!/usr/bin/env ruby
require 'xcodeproj'

project_path = File.join(__dir__, 'ios', 'Runner.xcodeproj')
project = Xcodeproj::Project.open(project_path)
runner = project.targets.find { |target| target.name == 'Runner' }
abort 'Runner target not found' unless runner

runner_group = project.main_group.find_subpath('Runner', false)
privacy_ref = runner_group.files.find { |f| f.path == 'PrivacyInfo.xcprivacy' } || runner_group.new_file('PrivacyInfo.xcprivacy')
unless runner.resources_build_phase.files_references.include?(privacy_ref)
  runner.resources_build_phase.add_file_reference(privacy_ref)
end

widget = project.targets.find { |target| target.name == 'OryntraWidget' }
unless widget
  widget = project.new_target(:app_extension, 'OryntraWidget', :ios, '14.0')
  widget.product_name = 'OryntraWidget'
end

main_group = project.main_group
widget_group = main_group.find_subpath('OryntraWidget', true)
widget_group.set_source_tree('<group>')

swift_ref = widget_group.files.find { |f| f.path == 'OryntraWidget.swift' } || widget_group.new_file('OryntraWidget.swift')
plist_ref = widget_group.files.find { |f| f.path == 'Info.plist' } || widget_group.new_file('Info.plist')
ent_ref = widget_group.files.find { |f| f.path == 'OryntraWidget.entitlements' } || widget_group.new_file('OryntraWidget.entitlements')

unless widget.source_build_phase.files_references.include?(swift_ref)
  widget.source_build_phase.add_file_reference(swift_ref)
end

widget.build_configurations.each do |config|
  config.build_settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'com.oryntraai.app.OryntraWidget'
  config.build_settings['INFOPLIST_FILE'] = 'OryntraWidget/Info.plist'
  config.build_settings['CODE_SIGN_ENTITLEMENTS'] = 'OryntraWidget/OryntraWidget.entitlements'
  config.build_settings['SWIFT_VERSION'] = '5.0'
  config.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = '14.0'
  config.build_settings['SKIP_INSTALL'] = 'YES'
  config.build_settings['APPLICATION_EXTENSION_API_ONLY'] = 'YES'
  config.build_settings['MARKETING_VERSION'] = '0.5.1'
  config.build_settings['CURRENT_PROJECT_VERSION'] = '4'
  config.build_settings['TARGETED_DEVICE_FAMILY'] = '1,2'
end

runner.build_configurations.each do |config|
  config.build_settings['CODE_SIGN_ENTITLEMENTS'] = 'Runner/Runner.entitlements'
  config.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = '14.0'
end

unless runner.dependencies.any? { |dependency| dependency.target == widget }
  runner.add_dependency(widget)
end

embed_phase = runner.copy_files_build_phases.find { |phase| phase.name == 'Embed App Extensions' }
unless embed_phase
  embed_phase = runner.new_copy_files_build_phase('Embed App Extensions')
  embed_phase.dst_subfolder_spec = '13'
end
unless embed_phase.files_references.include?(widget.product_reference)
  embed_phase.add_file_reference(widget.product_reference, true)
end

project.save
puts 'OryntraWidget target configured.'
