#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

"""
Configuration Management Tool - Quickly create, view, and modify workflow configurations

Usage:
    # View task configuration
    python manage_config.py show task_data/my_task
    
    # Create default configuration
    python manage_config.py init task_data/my_task
    
    # View generation records
    python manage_config.py records task_data/my_task
    
    # View generation history of a file
    python manage_config.py history task_data/my_task --file images/image_0_first.png
    
    # Export summary
    python manage_config.py summary task_data/my_task
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))
from config_manager import ConfigManager


def cmd_show(args):
    """Display task configuration"""
    config_file = os.path.join(args.task_path, 'workflow_config.json')
    
    if not os.path.exists(config_file):
        print(f"❌ Configuration file does not exist: {config_file}")
        print(f"💡 Use 'python manage_config.py init {args.task_path}' to create")
        return
    
    with open(config_file) as f:
        config = json.load(f)
    
    print(f"\n📋 Task Configuration: {args.task_path}")
    print("=" * 70)
    
    # Display configuration for each node
    node_types = ['image_generation', 'video_generation', 'tts', 'bgm']
    for node_type in node_types:
        if node_type in config:
            node_config = config[node_type]
            print(f"\n🔧 {node_type}")
            print(f"   Model: {node_config.get('model', 'N/A')}")
            print(f"   Enabled: {node_config.get('enabled', True)}")
            
            params = node_config.get('parameters', {})
            if params:
                print(f"   Parameters:")
                for key, value in params.items():
                    print(f"      {key}: {value}")
            else:
                print(f"   Parameters: (using defaults)")
    
    # Display global settings
    if 'global_settings' in config:
        print(f"\n🌐 Global Settings")
        for key, value in config['global_settings'].items():
            print(f"   {key}: {value}")


def cmd_init(args):
    """Initialize configuration"""
    if not os.path.exists(args.task_path):
        os.makedirs(args.task_path)
        print(f"📁 Created task directory: {args.task_path}")
    
    manager = ConfigManager(args.task_path)
    print(f"✅ Configuration initialized: {args.task_path}/workflow_config.json")
    
    # Display configuration path
    print(f"\n📝 Configuration file location:")
    print(f"   {os.path.abspath(manager.config_file)}")
    print(f"\n💡 Next steps:")
    print(f"   1. Edit config: vim {manager.config_file}")
    print(f"   2. View config: python manage_config.py show {args.task_path}")
    print(f"   3. Run workflow")


def cmd_records(args):
    """View generation records"""
    records_file = os.path.join(args.task_path, 'generation_records.json')
    
    if not os.path.exists(records_file):
        print(f"❌ Records file does not exist: {records_file}")
        print(f"💡 Records file will be auto-generated after workflow runs")
        return
    
    with open(records_file) as f:
        records = json.load(f)
    
    print(f"\n📊 Generation Records: {args.task_path}")
    print("=" * 70)
    
    summary = records.get('summary', {})
    print(f"\n📈 Statistics Summary:")
    print(f"   Total Images: {summary.get('total_images', 0)}")
    print(f"   Total Videos: {summary.get('total_videos', 0)}")
    print(f"   Total Audios: {summary.get('total_audios', 0)}")
    print(f"   Total BGM: {summary.get('total_bgm', 0)}")
    print(f"   Total Generation Time: {summary.get('total_generation_time', 0):.2f} seconds")
    
    # Display recent records
    all_records = []
    for category, cat_records in records.get('records', {}).items():
        for record in cat_records:
            record['category'] = category
            all_records.append(record)
    
    # Sort by time
    all_records.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    if all_records:
        print(f"\n📝 Recent Generations (top {min(5, len(all_records))}):")
        for i, record in enumerate(all_records[:5], 1):
            print(f"\n   [{i}] {record['category']} - {os.path.basename(record['output_path'])}")
            print(f"       Time: {record.get('timestamp', 'N/A')}")
            print(f"       Model: {record.get('model', 'N/A')}")
            print(f"       Node: {record.get('node', 'N/A')}")
            
            metadata = record.get('metadata', {})
            if 'generation_time' in metadata:
                print(f"       Generation Time: {metadata['generation_time']:.2f}s")


def cmd_history(args):
    """View generation history of a file"""
    manager = ConfigManager(args.task_path)
    
    # Build full path
    if args.file.startswith(args.task_path):
        file_path = args.file
    else:
        file_path = os.path.join(args.task_path, args.file)
    
    history = manager.get_generation_history(output_path=file_path)
    
    if not history:
        print(f"❌ No generation record found for file: {args.file}")
        return
    
    print(f"\n📜 File Generation History: {args.file}")
    print("=" * 70)
    
    for i, record in enumerate(history, 1):
        print(f"\n[Record {i}] {record.get('timestamp', 'N/A')}")
        print(f"Node: {record.get('node', 'N/A')}")
        print(f"Model: {record.get('model', 'N/A')}")
        
        print(f"\nInputs:")
        inputs = record.get('inputs', {})
        for key, value in inputs.items():
            if isinstance(value, str) and len(value) > 60:
                value = value[:60] + '...'
            print(f"  {key}: {value}")
        
        print(f"\nParameters:")
        params = record.get('parameters', {})
        for key, value in params.items():
            print(f"  {key}: {value}")
        
        print(f"\nMetadata:")
        metadata = record.get('metadata', {})
        for key, value in metadata.items():
            print(f"  {key}: {value}")


def cmd_summary(args):
    """Export task summary"""
    manager = ConfigManager(args.task_path)
    summary = manager.export_summary()
    
    if args.json:
        # Output JSON format
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        # Friendly format
        print(f"\n📊 Task Summary: {args.task_path}")
        print("=" * 70)
        
        print(f"\n📋 Configuration Info:")
        for node_type in ['image_generation', 'video_generation', 'tts', 'bgm']:
            if node_type in summary['config']:
                model = summary['config'][node_type].get('model', 'N/A')
                print(f"   {node_type}: {model}")
        
        print(f"\n📈 Generation Statistics:")
        for key, value in summary['summary'].items():
            print(f"   {key}: {value}")
        
        print(f"\n📝 Total Records: {summary['total_records']}")


def cmd_compare(args):
    """Compare configurations of two tasks"""
    task1_config = os.path.join(args.task_path_1, 'workflow_config.json')
    task2_config = os.path.join(args.task_path_2, 'workflow_config.json')
    
    if not os.path.exists(task1_config):
        print(f"❌ Configuration does not exist: {task1_config}")
        return
    if not os.path.exists(task2_config):
        print(f"❌ Configuration does not exist: {task2_config}")
        return
    
    with open(task1_config) as f:
        config1 = json.load(f)
    with open(task2_config) as f:
        config2 = json.load(f)
    
    print(f"\n⚖️  Configuration Comparison")
    print("=" * 70)
    print(f"Task 1: {args.task_path_1}")
    print(f"Task 2: {args.task_path_2}")
    
    # Compare configuration for each node
    node_types = ['image_generation', 'video_generation', 'tts', 'bgm']
    for node_type in node_types:
        params1 = config1.get(node_type, {}).get('parameters', {})
        params2 = config2.get(node_type, {}).get('parameters', {})
        
        if params1 != params2:
            print(f"\n🔧 {node_type} Parameter Differences:")
            
            all_keys = set(params1.keys()) | set(params2.keys())
            for key in sorted(all_keys):
                val1 = params1.get(key, '(not set)')
                val2 = params2.get(key, '(not set)')
                
                if val1 != val2:
                    print(f"   {key}:")
                    print(f"      Task 1: {val1}")
                    print(f"      Task 2: {val2}")
        else:
            print(f"\n✅ {node_type}: Configurations are identical")


def main():
    parser = argparse.ArgumentParser(
        description='Workflow Configuration Management Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize configuration
  python manage_config.py init task_data/my_task
  
  # View configuration
  python manage_config.py show task_data/my_task
  
  # View generation records
  python manage_config.py records task_data/my_task
  
  # View file history
  python manage_config.py history task_data/my_task --file images/image_0_first.png
  
  # Export summary
  python manage_config.py summary task_data/my_task
  
  # Compare two task configurations
  python manage_config.py compare task_data/task1 task_data/task2
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # show command
    parser_show = subparsers.add_parser('show', help='View task configuration')
    parser_show.add_argument('task_path', help='Task path')
    
    # init command
    parser_init = subparsers.add_parser('init', help='Initialize configuration')
    parser_init.add_argument('task_path', help='Task path')
    
    # records command
    parser_records = subparsers.add_parser('records', help='View generation records')
    parser_records.add_argument('task_path', help='Task path')
    
    # history command
    parser_history = subparsers.add_parser('history', help='View file generation history')
    parser_history.add_argument('task_path', help='Task path')
    parser_history.add_argument('--file', required=True, help='File path (relative to task path)')
    
    # summary command
    parser_summary = subparsers.add_parser('summary', help='Export task summary')
    parser_summary.add_argument('task_path', help='Task path')
    parser_summary.add_argument('--json', action='store_true', help='Output in JSON format')
    
    # compare command
    parser_compare = subparsers.add_parser('compare', help='Compare configurations of two tasks')
    parser_compare.add_argument('task_path_1', help='Task 1 path')
    parser_compare.add_argument('task_path_2', help='Task 2 path')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Execute command
    if args.command == 'show':
        cmd_show(args)
    elif args.command == 'init':
        cmd_init(args)
    elif args.command == 'records':
        cmd_records(args)
    elif args.command == 'history':
        cmd_history(args)
    elif args.command == 'summary':
        cmd_summary(args)
    elif args.command == 'compare':
        cmd_compare(args)


if __name__ == '__main__':
    main()
