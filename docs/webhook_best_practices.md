# Webhook使用案例

通过Webhook可以做的案例思路：
- [案例1: 通过Lambda监控AWS费用异常](#案例1-通过lambda监控aws费用异常)
- [案例2: 通过Lambda监控CloudWatch异常](#案例2-通过lambda监控cloudwatch异常)
- [案例3: 通过CloudEvents触发Lambda做云事件监控](#案例3-通过cloudevents触发lambda做云事件监控)
- [案例4: 定期汇总服务健康状态](#案例4-定期汇总服务健康状态)
- [案例5: 监控数据库性能指标](#案例5-监控数据库性能指标)
- [案例6: CI/CD管道状态通知](#案例6-cicd管道状态通知)

## 案例1: 通过Lambda监控AWS费用异常

这个案例展示如何使用AWS Lambda监控费用异常，并通过Webhook将费用异常报告发送给飞书。

### 1. 设置Webhook
在飞书机器人中创建一个名为"费用异常监控"的Webhook:
- 名称: 费用异常监控
- 描述: 监控AWS账单异常波动并通知团队
- 模型: 选择一个适合分析数据的模型
- 提示词模板: 
```
请分析以下AWS费用异常数据，提取关键信息，包括:
1. 哪些服务的费用异常增长
2. 异常增长的幅度和趋势
3. 可能的原因分析
4. 建议的优化措施

数据：{data}
```

### 2. Lambda代码实现

```python
import json
import boto3
import urllib.request
import datetime
import urllib.parse

# 配置参数
WEBHOOK_URL = "https://your-lark-bot-domain.com/api/webhook/your-webhook-token"
THRESHOLD_PERCENT = 30  # 异常阈值百分比
AWS_REGION = "us-east-1"

def lambda_handler(event, context):
    # 初始化Cost Explorer客户端
    ce_client = boto3.client('ce', region_name=AWS_REGION)
    
    # 获取当前日期和上个月同期日期
    today = datetime.datetime.now()
    end_date = today.strftime('%Y-%m-%d')
    
    # 获取过去7天的数据
    start_date = (today - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
    
    # 获取前一个周期的日期范围(对比数据)
    previous_period_start = (today - datetime.timedelta(days=14)).strftime('%Y-%m-%d')
    previous_period_end = (today - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
    
    # 查询当前周期的费用数据
    current_cost_response = ce_client.get_cost_and_usage(
        TimePeriod={
            'Start': start_date,
            'End': end_date
        },
        Granularity='DAILY',
        Metrics=['UnblendedCost'],
        GroupBy=[
            {
                'Type': 'DIMENSION',
                'Key': 'SERVICE'
            }
        ]
    )
    
    # 查询前一个周期的费用数据
    previous_cost_response = ce_client.get_cost_and_usage(
        TimePeriod={
            'Start': previous_period_start,
            'End': previous_period_end
        },
        Granularity='DAILY',
        Metrics=['UnblendedCost'],
        GroupBy=[
            {
                'Type': 'DIMENSION',
                'Key': 'SERVICE'
            }
        ]
    )
    
    # 分析费用变化
    anomalies = analyze_cost_changes(current_cost_response, previous_cost_response)
    
    # 如果有异常，发送通知
    if anomalies:
        send_notification(anomalies)
        return {
            'statusCode': 200,
            'body': json.dumps('Cost anomalies detected and notification sent!')
        }
    else:
        return {
            'statusCode': 200,
            'body': json.dumps('No cost anomalies detected.')
        }

def analyze_cost_changes(current_data, previous_data):
    # 聚合服务费用
    current_service_costs = {}
    previous_service_costs = {}
    
    # 处理当前周期数据
    for day_data in current_data['ResultsByTime']:
        for group in day_data['Groups']:
            service = group['Keys'][0]
            cost = float(group['Metrics']['UnblendedCost']['Amount'])
            
            if service in current_service_costs:
                current_service_costs[service] += cost
            else:
                current_service_costs[service] = cost
    
    # 处理前一周期数据
    for day_data in previous_data['ResultsByTime']:
        for group in day_data['Groups']:
            service = group['Keys'][0]
            cost = float(group['Metrics']['UnblendedCost']['Amount'])
            
            if service in previous_service_costs:
                previous_service_costs[service] += cost
            else:
                previous_service_costs[service] = cost
    
    # 检测异常
    anomalies = []
    for service, current_cost in current_service_costs.items():
        previous_cost = previous_service_costs.get(service, 0)
        
        # 避免除零错误
        if previous_cost == 0:
            if current_cost > 1:  # 1美元门槛
                percent_increase = 100  # 设置为100%增长
            else:
                continue
        else:
            percent_increase = ((current_cost - previous_cost) / previous_cost) * 100
        
        # 检查是否超过阈值
        if percent_increase > THRESHOLD_PERCENT:
            anomalies.append({
                "service": service,
                "current_cost": current_cost,
                "previous_cost": previous_cost,
                "percent_increase": percent_increase
            })
    
    return anomalies

def send_notification(anomalies):
    # 构建通知内容
    notification_data = {
        "event_type": "cost_anomaly",
        "anomalies": anomalies,
        "detection_time": datetime.datetime.now().isoformat(),
        "account_id": boto3.client('sts').get_caller_identity().get('Account')
    }
    
    # 发送到Webhook
    data = json.dumps(notification_data).encode('utf-8')
    headers = {
        'Content-Type': 'application/json'
    }
    
    req = urllib.request.Request(WEBHOOK_URL, data=data, headers=headers)
    
    try:
        with urllib.request.urlopen(req) as response:
            print(f"Notification sent, response: {response.read().decode()}")
    except Exception as e:
        print(f"Error sending notification: {e}")
```

### 3. 部署步骤
1. 创建新的Lambda函数，并粘贴上述代码
2. 设置适当的IAM权限，确保Lambda有权访问Cost Explorer API
3. 设置CloudWatch Events/EventBridge规则，按计划（如每天）触发Lambda
4. 配置环境变量中的WEBHOOK_URL为您在飞书机器人中创建的Webhook URL

## 案例2: 通过Lambda监控CloudWatch异常

这个案例展示如何监控CloudWatch告警，并将异常事件通过Webhook发送给飞书进行AI分析和通知。

### 1. 设置Webhook
在飞书机器人中创建一个名为"CloudWatch监控"的Webhook:
- 名称: CloudWatch监控
- 描述: 监控AWS CloudWatch告警并分析
- 模型: 选择一个适合分析运维数据的模型
- 提示词模板: 
```
请分析以下AWS CloudWatch告警数据，并提供以下信息：
1. 告警摘要和严重程度评估
2. 可能的原因分析
3. 建议的应急处理步骤
4. 相关服务和资源的影响分析

告警数据：{data}
```

### 2. Lambda代码实现

```python
import json
import boto3
import urllib.request
import urllib.parse
import datetime
import os

# 配置参数
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

def lambda_handler(event, context):
    print("Received event:", json.dumps(event))
    
    # 处理CloudWatch告警事件
    if 'detail-type' in event and event['detail-type'] == 'CloudWatch Alarm State Change':
        alarm_data = process_cloudwatch_alarm(event)
        send_webhook_notification(alarm_data)
        return {
            'statusCode': 200,
            'body': json.dumps('Processed CloudWatch alarm and sent notification')
        }
    
    # 也支持SNS消息格式
    elif 'Records' in event and event['Records'][0].get('EventSource') == 'aws:sns':
        sns_message = json.loads(event['Records'][0]['Sns']['Message'])
        if 'AlarmName' in sns_message:
            alarm_data = process_sns_alarm(sns_message)
            send_webhook_notification(alarm_data)
            return {
                'statusCode': 200,
                'body': json.dumps('Processed SNS alarm message and sent notification')
            }
    
    return {
        'statusCode': 400,
        'body': json.dumps('Unsupported event type')
    }

def process_cloudwatch_alarm(event):
    detail = event['detail']
    alarm_name = detail['alarmName']
    state = detail['state']['value']  # OK, ALARM, INSUFFICIENT_DATA
    previous_state = detail['previousState']['value']
    reason = detail['state']['reason']
    timestamp = detail['state']['timestamp']
    
    # 获取更详细的告警信息
    cloudwatch = boto3.client('cloudwatch', region_name=AWS_REGION)
    alarm_details = cloudwatch.describe_alarms(AlarmNames=[alarm_name])
    
    metric_info = {}
    if 'MetricAlarms' in alarm_details and alarm_details['MetricAlarms']:
        metric_alarm = alarm_details['MetricAlarms'][0]
        metric_info = {
            'namespace': metric_alarm.get('Namespace'),
            'metric_name': metric_alarm.get('MetricName'),
            'dimensions': metric_alarm.get('Dimensions', []),
            'period': metric_alarm.get('Period'),
            'statistic': metric_alarm.get('Statistic'),
            'threshold': metric_alarm.get('Threshold'),
            'comparison_operator': metric_alarm.get('ComparisonOperator'),
            'evaluation_periods': metric_alarm.get('EvaluationPeriods')
        }
    
    # 尝试获取最近的指标数据点
    recent_datapoints = []
    try:
        if metric_info and 'namespace' in metric_info and 'metric_name' in metric_info:
            end_time = datetime.datetime.now()
            start_time = end_time - datetime.timedelta(hours=1)
            
            dimensions = []
            for dim in metric_info.get('dimensions', []):
                dimensions.append({
                    'Name': dim.get('Name', ''),
                    'Value': dim.get('Value', '')
                })
            
            response = cloudwatch.get_metric_data(
                MetricDataQueries=[
                    {
                        'Id': 'metric1',
                        'MetricStat': {
                            'Metric': {
                                'Namespace': metric_info['namespace'],
                                'MetricName': metric_info['metric_name'],
                                'Dimensions': dimensions
                            },
                            'Period': 60,
                            'Stat': metric_info.get('statistic', 'Average')
                        },
                        'ReturnData': True
                    }
                ],
                StartTime=start_time,
                EndTime=end_time
            )
            
            if 'MetricDataResults' in response:
                for result in response['MetricDataResults']:
                    timestamps = result.get('Timestamps', [])
                    values = result.get('Values', [])
                    for i in range(min(len(timestamps), len(values))):
                        recent_datapoints.append({
                            'timestamp': timestamps[i].isoformat(),
                            'value': values[i]
                        })
    except Exception as e:
        print(f"Error getting metric data: {e}")
    
    # 构建完整的告警数据
    alarm_data = {
        'event_type': 'cloudwatch_alarm',
        'alarm_name': alarm_name,
        'state': state,
        'previous_state': previous_state,
        'reason': reason,
        'timestamp': timestamp,
        'metric_info': metric_info,
        'recent_datapoints': recent_datapoints,
        'region': AWS_REGION,
        'account_id': context.invoked_function_arn.split(':')[4]
    }
    
    return alarm_data

def process_sns_alarm(sns_message):
    # 处理SNS格式的CloudWatch告警
    alarm_data = {
        'event_type': 'cloudwatch_alarm',
        'alarm_name': sns_message.get('AlarmName'),
        'state': sns_message.get('NewStateValue'),
        'previous_state': sns_message.get('OldStateValue'),
        'reason': sns_message.get('NewStateReason'),
        'timestamp': sns_message.get('StateChangeTime'),
        'metric_info': {
            'namespace': sns_message.get('Namespace'),
            'metric_name': sns_message.get('MetricName'),
            'dimensions': sns_message.get('Dimensions', []),
            'period': sns_message.get('Period'),
            'statistic': sns_message.get('Statistic'),
            'threshold': sns_message.get('Threshold'),
            'comparison_operator': sns_message.get('ComparisonOperator'),
        },
        'region': AWS_REGION
    }
    
    return alarm_data

def send_webhook_notification(alarm_data):
    # 发送到Webhook
    data = json.dumps(alarm_data).encode('utf-8')
    headers = {
        'Content-Type': 'application/json'
    }
    
    req = urllib.request.Request(WEBHOOK_URL, data=data, headers=headers)
    
    try:
        with urllib.request.urlopen(req) as response:
            print(f"Notification sent, response: {response.read().decode()}")
    except Exception as e:
        print(f"Error sending notification: {e}")
```

### 3. 部署步骤
1. 创建新的Lambda函数，并粘贴上述代码
2. 设置环境变量:
   - WEBHOOK_URL: 您在飞书机器人中创建的Webhook URL
   - AWS_REGION: 您希望监控的AWS区域
3. 设置IAM权限，确保Lambda有权访问CloudWatch API
4. 配置以下触发器之一:
   - CloudWatch Events/EventBridge规则，订阅CloudWatch告警状态变化事件
   - SNS主题，配置为CloudWatch告警的通知目标

## 案例3: 通过CloudEvents触发Lambda做云事件监控

这个案例展示如何使用CloudEvents标准格式的事件触发Lambda函数，并通过Webhook向飞书发送智能分析结果。

### 1. 设置Webhook
在飞书机器人中创建一个名为"云事件监控"的Webhook:
- 名称: 云事件监控
- 描述: 通过CloudEvents监控AWS云事件
- 模型: 选择一个适合安全分析的模型
- 提示词模板: 
```
请分析以下云事件数据，提供安全评估和建议：
1. 事件类型和严重性分析
2. 是否存在安全风险或异常行为
3. 涉及到的资源和服务
4. 建议的响应措施

请结构化输出，使用Markdown格式增强可读性。
事件数据：{data}
```

### 2. Lambda代码实现

```python
import json
import boto3
import urllib.request
import urllib.parse
import datetime
import os
import uuid
import base64

# 配置参数
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
SEVERITY_THRESHOLD = os.environ.get('SEVERITY_THRESHOLD', 'INFO')  # DEBUG, INFO, WARN, ERROR, CRITICAL

# 严重性映射
SEVERITY_LEVELS = {
    'DEBUG': 0,
    'INFO': 1,
    'WARN': 2,
    'ERROR': 3,
    'CRITICAL': 4
}

def lambda_handler(event, context):
    print("Received event:", json.dumps(event))
    
    # 确定事件类型
    event_type = identify_event_type(event)
    
    # 根据事件类型处理事件
    if event_type == 'cloudevents':
        processed_event = process_cloudevents(event)
    elif event_type == 'eventbridge':
        processed_event = process_eventbridge(event)
    elif event_type == 'guardduty':
        processed_event = process_guardduty(event)
    elif event_type == 'securityhub':
        processed_event = process_securityhub(event)
    elif event_type == 'config':
        processed_event = process_config(event)
    else:
        processed_event = process_generic_event(event)
    
    # 根据严重性决定是否发送通知
    if should_send_notification(processed_event.get('severity', 'INFO')):
        send_webhook_notification(processed_event)
        return {
            'statusCode': 200,
            'body': json.dumps('Event processed and notification sent')
        }
    else:
        return {
            'statusCode': 200,
            'body': json.dumps('Event processed but severity below threshold')
        }

def identify_event_type(event):
    """确定事件的类型"""
    # 检查是否是CloudEvents格式
    if 'specversion' in event and 'type' in event:
        return 'cloudevents'
    
    # 检查是否是EventBridge格式
    if 'detail-type' in event and 'source' in event:
        # 具体服务类型
        if event['source'] == 'aws.guardduty':
            return 'guardduty'
        elif event['source'] == 'aws.securityhub':
            return 'securityhub'
        elif event['source'] == 'aws.config':
            return 'config'
        return 'eventbridge'
    
    # 默认为通用事件
    return 'generic'

def process_cloudevents(event):
    """处理CloudEvents格式的事件"""
    event_time = event.get('time', datetime.datetime.now().isoformat())
    event_type = event.get('type', 'unknown')
    event_source = event.get('source', 'unknown')
    event_id = event.get('id', str(uuid.uuid4()))
    
    # 处理数据
    data = event.get('data', {})
    if isinstance(data, str):
        try:
            # 尝试解析为JSON
            data = json.loads(data)
        except:
            # 检查是否是base64编码
            try:
                decoded = base64.b64decode(data).decode('utf-8')
                data = json.loads(decoded)
            except:
                pass
    
    # 确定严重性
    severity = determine_severity(event, data)
    
    # 构建标准化的事件
    processed_event = {
        'event_id': event_id,
        'event_type': event_type,
        'event_source': event_source,
        'event_time': event_time,
        'severity': severity,
        'data': data,
        'original_format': 'cloudevents'
    }
    
    return processed_event

def process_eventbridge(event):
    """处理EventBridge格式的事件"""
    event_time = event.get('time', datetime.datetime.now().isoformat())
    event_type = event.get('detail-type', 'unknown')
    event_source = event.get('source', 'unknown')
    event_id = event.get('id', str(uuid.uuid4()))
    
    # 提取详细数据
    detail = event.get('detail', {})
    
    # 确定严重性
    severity = determine_severity(event, detail)
    
    # 构建标准化的事件
    processed_event = {
        'event_id': event_id,
        'event_type': event_type,
        'event_source': event_source,
        'event_time': event_time,
        'severity': severity,
        'data': detail,
        'resources': event.get('resources', []),
        'region': event.get('region', AWS_REGION),
        'account': event.get('account', ''),
        'original_format': 'eventbridge'
    }
    
    return processed_event

def process_guardduty(event):
    """处理GuardDuty格式的事件"""
    detail = event.get('detail', {})
    
    # GuardDuty特有的字段
    finding_id = detail.get('id', '')
    finding_type = detail.get('type', '')
    severity = 'INFO'
    
    # GuardDuty严重性转换
    severity_score = detail.get('severity', 0)
    if severity_score >= 7:
        severity = 'CRITICAL'
    elif severity_score >= 4:
        severity = 'ERROR'
    elif severity_score >= 1:
        severity = 'WARN'
    
    # 构建标准化的事件
    processed_event = {
        'event_id': event.get('id', finding_id),
        'event_type': 'guardduty_finding',
        'event_source': event.get('source', 'aws.guardduty'),
        'event_time': event.get('time', detail.get('updatedAt', '')),
        'severity': severity,
        'finding_id': finding_id,
        'finding_type': finding_type,
        'severity_score': severity_score,
        'title': detail.get('title', ''),
        'description': detail.get('description', ''),
        'account_id': detail.get('accountId', ''),
        'region': detail.get('region', AWS_REGION),
        'data': detail,
        'resources': event.get('resources', []),
        'original_format': 'guardduty'
    }
    
    return processed_event

def process_securityhub(event):
    """处理SecurityHub格式的事件"""
    detail = event.get('detail', {})
    finding = detail.get('findings', [{}])[0] if detail.get('findings') else {}
    
    # SecurityHub特有的字段
    finding_id = finding.get('Id', '')
    finding_type = finding.get('Types', [''])[0] if finding.get('Types') else ''
    
    # 严重性映射
    severity_label = finding.get('Severity', {}).get('Label', 'INFORMATIONAL')
    severity = 'INFO'
    if severity_label == 'CRITICAL':
        severity = 'CRITICAL'
    elif severity_label == 'HIGH':
        severity = 'ERROR'
    elif severity_label == 'MEDIUM':
        severity = 'WARN'
    elif severity_label == 'LOW':
        severity = 'INFO'
    
    # 构建标准化的事件
    processed_event = {
        'event_id': event.get('id', finding_id),
        'event_type': 'securityhub_finding',
        'event_source': event.get('source', 'aws.securityhub'),
        'event_time': event.get('time', finding.get('UpdatedAt', '')),
        'severity': severity,
        'finding_id': finding_id,
        'finding_type': finding_type,
        'title': finding.get('Title', ''),
        'description': finding.get('Description', ''),
        'account_id': finding.get('AwsAccountId', ''),
        'region': finding.get('Region', AWS_REGION),
        'resources': finding.get('Resources', []),
        'data': finding,
        'original_format': 'securityhub'
    }
    
    return processed_event

def process_config(event):
    """处理AWS Config格式的事件"""
    detail = event.get('detail', {})
    
    # Config特有的字段
    config_rule = detail.get('configRuleName', '')
    resource_type = detail.get('resourceType', '')
    resource_id = detail.get('resourceId', '')
    compliance = detail.get('newEvaluationResult', {}).get('complianceType', '')
    
    # 根据合规性确定严重性
    severity = 'INFO'
    if compliance == 'NON_COMPLIANT':
        severity = 'WARN'
    
    # 构建标准化的事件
    processed_event = {
        'event_id': event.get('id', str(uuid.uuid4())),
        'event_type': 'config_compliance_change',
        'event_source': event.get('source', 'aws.config'),
        'event_time': event.get('time', datetime.datetime.now().isoformat()),
        'severity': severity,
        'config_rule': config_rule,
        'resource_type': resource_type,
        'resource_id': resource_id,
        'compliance': compliance,
        'account_id': event.get('account', ''),
        'region': event.get('region', AWS_REGION),
        'data': detail,
        'original_format': 'config'
    }
    
    return processed_event

def process_generic_event(event):
    """处理通用事件"""
    # 尽可能提取有用信息
    event_time = datetime.datetime.now().isoformat()
    if isinstance(event, dict):
        # 尝试找到常见的时间字段
        for time_key in ['timestamp', 'eventTime', 'time', 'createdAt', 'date']:
            if time_key in event:
                event_time = event[time_key]
                break
    
    # 确定严重性
    severity = determine_severity(event, {})
    
    # 构建标准化的事件
    processed_event = {
        'event_id': str(uuid.uuid4()),
        'event_type': 'generic_event',
        'event_source': 'unknown',
        'event_time': event_time,
        'severity': severity,
        'data': event,
        'original_format': 'generic'
    }
    
    return processed_event

def determine_severity(event, detail):
    """根据事件内容判断严重性"""
    # 默认严重性
    severity = 'INFO'
    
    # 检查CloudEvents的扩展属性
    if 'severity' in event:
        return event['severity'].upper()
    
    # 从事件内容推断严重性
    if isinstance(detail, dict):
        # 检查常见的严重性字段
        if 'severity' in detail:
            severity_val = detail['severity']
            if isinstance(severity_val, str):
                return severity_val.upper()
            elif isinstance(severity_val, (int, float)):
                # 数值严重性转换为字符串级别
                if severity_val >= 70:
                    return 'CRITICAL'
                elif severity_val >= 40:
                    return 'ERROR'
                elif severity_val >= 20:
                    return 'WARN'
        
        # 检查事件类型关键词
        event_keywords = {
            'CRITICAL': ['critical', 'emergency', 'fatal', 'failure', 'breach', 'attack', 'compromise'],
            'ERROR': ['error', 'fail', 'failed', 'unauthorized', 'denied', 'violation'],
            'WARN': ['warning', 'suspicious', 'anomaly', 'unusual']
        }
        
        # 将事件转为字符串进行关键词搜索
        event_str = json.dumps(detail).lower()
        
        for level, keywords in event_keywords.items():
            for keyword in keywords:
                if keyword in event_str:
                    return level
    
    return severity

def should_send_notification(severity):
    """根据严重性决定是否应该发送通知"""
    threshold = SEVERITY_THRESHOLD.upper()
    
    if threshold not in SEVERITY_LEVELS:
        # 默认为INFO
        threshold = 'INFO'
    
    severity = severity.upper()
    if severity not in SEVERITY_LEVELS:
        # 未知严重性视为INFO
        severity = 'INFO'
    
    # 只有当事件严重性大于等于阈值时才发送通知
    return SEVERITY_LEVELS[severity] >= SEVERITY_LEVELS[threshold]

def send_webhook_notification(event_data):
    # 补充一些元数据
    event_data['notification_time'] = datetime.datetime.now().isoformat()
    event_data['aws_region'] = os.environ.get('AWS_REGION', 'unknown')
    
    # 发送到Webhook
    data = json.dumps(event_data).encode('utf-8')
    headers = {
        'Content-Type': 'application/json'
    }
    
    req = urllib.request.Request(WEBHOOK_URL, data=data, headers=headers)
    
    try:
        with urllib.request.urlopen(req) as response:
            print(f"Notification sent, response: {response.read().decode()}")
    except Exception as e:
        print(f"Error sending notification: {e}")
```

### 3. 部署步骤
1. 创建新的Lambda函数，并粘贴上述代码
2. 设置环境变量:
   - WEBHOOK_URL: 您在飞书机器人中创建的Webhook URL
   - SEVERITY_THRESHOLD: 设置通知阈值(DEBUG/INFO/WARN/ERROR/CRITICAL)
3. 设置触发器:
   - EventBridge规则，捕获感兴趣的事件，如GuardDuty发现、SecurityHub结果、EC2状态变更等
   - API Gateway配置为接收CloudEvents格式的事件
4. 设置适当的IAM权限

## 更多Webhook使用案例

### 案例4: 定期汇总服务健康状态

```python
import json
import boto3
import urllib.request
import datetime
import time

WEBHOOK_URL = "https://your-lark-bot-domain.com/api/webhook/your-webhook-token"

def lambda_handler(event, context):
    # 收集所有区域的服务健康状态
    health_client = boto3.client('health', region_name='us-east-1')  # Health API在所有区域可用
    
    # 获取影响服务的事件
    try:
        response = health_client.describe_events(
            filter={
                'eventStatusCodes': ['open', 'upcoming'],
                'eventTypeCategories': ['issue', 'accountNotification', 'scheduledChange']
            }
        )
        
        events = response.get('events', [])
        
        # 获取每个事件的详细信息
        detailed_events = []
        for event in events:
            event_details = health_client.describe_event_details(
                eventArns=[event['arn']]
            )
            
            if 'successfulSet' in event_details and event_details['successfulSet']:
                detail = event_details['successfulSet'][0]
                event_info = {
                    'arn': event['arn'],
                    'service': event['service'],
                    'eventTypeCode': event['eventTypeCode'],
                    'status': event['statusCode'],
                    'region': event.get('region', 'global'),
                    'startTime': event.get('startTime', '').isoformat() if event.get('startTime') else None,
                    'endTime': event.get('endTime', '').isoformat() if event.get('endTime') else None,
                    'lastUpdatedTime': event.get('lastUpdatedTime', '').isoformat() if event.get('lastUpdatedTime') else None,
                    'eventDescription': detail.get('eventDescription', {}).get('latestDescription', '')
                }
                detailed_events.append(event_info)
        
        # 获取资源状态概览 (EC2, RDS等)
        ec2_status = get_ec2_status()
        rds_status = get_rds_status()
        s3_status = get_s3_status()
        lambda_status = get_lambda_status()
        
        # 汇总报告
        health_report = {
            'report_type': 'service_health_summary',
            'timestamp': datetime.datetime.now().isoformat(),
            'health_events': detailed_events,
            'service_status': {
                'ec2': ec2_status,
                'rds': rds_status,
                's3': s3_status,
                'lambda': lambda_status
            }
        }
        
        # 发送报告
        send_webhook_notification(health_report)
        
        return {
            'statusCode': 200,
            'body': json.dumps('Service health report generated and sent')
        }
        
    except Exception as e:
        print(f"Error generating health report: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }

def get_ec2_status():
    """获取EC2实例状态概览"""
    try:
        ec2_client = boto3.client('ec2')
        response = ec2_client.describe_instance_status()
        
        total_instances = len(response.get('InstanceStatuses', []))
        ok_instances = 0
        impaired_instances = 0
        
        for status in response.get('InstanceStatuses', []):
            if status.get('InstanceStatus', {}).get('Status') == 'ok' and \
               status.get('SystemStatus', {}).get('Status') == 'ok':
                ok_instances += 1
            else:
                impaired_instances += 1
        
        return {
            'total': total_instances,
            'healthy': ok_instances,
            'impaired': impaired_instances
        }
    except Exception as e:
        print(f"Error getting EC2 status: {e}")
        return {'error': str(e)}

def get_rds_status():
    """获取RDS实例状态概览"""
    try:
        rds_client = boto3.client('rds')
        response = rds_client.describe_db_instances()
        
        total_instances = len(response.get('DBInstances', []))
        available_instances = 0
        other_instances = 0
        
        for instance in response.get('DBInstances', []):
            if instance.get('DBInstanceStatus') == 'available':
                available_instances += 1
            else:
                other_instances += 1
        
        return {
            'total': total_instances,
            'available': available_instances,
            'other_status': other_instances
        }
    except Exception as e:
        print(f"Error getting RDS status: {e}")
        return {'error': str(e)}

def get_s3_status():
    """获取S3存储桶状态概览"""
    try:
        s3_client = boto3.client('s3')
        response = s3_client.list_buckets()
        
        total_buckets = len(response.get('Buckets', []))
        
        return {
            'total_buckets': total_buckets
        }
    except Exception as e:
        print(f"Error getting S3 status: {e}")
        return {'error': str(e)}

def get_lambda_status():
    """获取Lambda函数状态概览"""
    try:
        lambda_client = boto3.client('lambda')
        response = lambda_client.list_functions()
        
        total_functions = len(response.get('Functions', []))
        
        return {
            'total_functions': total_functions
        }
    except Exception as e:
        print(f"Error getting Lambda status: {e}")
        return {'error': str(e)}

def send_webhook_notification(data):
    # 发送到Webhook
    data_bytes = json.dumps(data).encode('utf-8')
    headers = {
        'Content-Type': 'application/json'
    }
    
    req = urllib.request.Request(WEBHOOK_URL, data=data_bytes, headers=headers)
    
    try:
        with urllib.request.urlopen(req) as response:
            print(f"Notification sent, response: {response.read().decode()}")
    except Exception as e:
        print(f"Error sending notification: {e}")
```

### 案例5: 监控数据库性能指标

```python
import json
import boto3
import urllib.request
import datetime
import statistics

WEBHOOK_URL = "https://your-lark-bot-domain.com/api/webhook/your-webhook-token"
RDS_INSTANCE_ID = "your-rds-instance-id"  # 您的RDS实例ID
EVALUATION_PERIOD = 24  # 小时

def lambda_handler(event, context):
    # 获取RDS性能指标
    end_time = datetime.datetime.now()
    start_time = end_time - datetime.timedelta(hours=EVALUATION_PERIOD)
    
    # 创建CloudWatch客户端
    cloudwatch = boto3.client('cloudwatch')
    
    # 定义要监控的指标
    metrics = [
        {"name": "CPUUtilization", "statistic": "Average", "unit": "Percent"},
        {"name": "DatabaseConnections", "statistic": "Average", "unit": "Count"},
        {"name": "FreeableMemory", "statistic": "Average", "unit": "Bytes"},
        {"name": "FreeStorageSpace", "statistic": "Average", "unit": "Bytes"},
        {"name": "ReadIOPS", "statistic": "Average", "unit": "Count/Second"},
        {"name": "WriteIOPS", "statistic": "Average", "unit": "Count/Second"},
        {"name": "ReadLatency", "statistic": "Average", "unit": "Seconds"},
        {"name": "WriteLatency", "statistic": "Average", "unit": "Seconds"}
    ]
    
    metric_data = {}
    
    # 获取各项指标数据
    for metric in metrics:
        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/RDS",
            MetricName=metric["name"],
            Dimensions=[
                {
                    'Name': 'DBInstanceIdentifier',
                    'Value': RDS_INSTANCE_ID
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,  # 1小时为一个数据点
            Statistics=[metric["statistic"]]
        )
        
        # 提取数据点
        datapoints = response.get('Datapoints', [])
        values = [dp.get(metric["statistic"]) for dp in datapoints if metric["statistic"] in dp]
        
        if values:
            avg_value = statistics.mean(values)
            max_value = max(values)
            min_value = min(values)
            
            # 适当的单位转换
            if metric["unit"] == "Bytes":
                avg_value = avg_value / (1024 * 1024 * 1024)  # 转换为GB
                max_value = max_value / (1024 * 1024 * 1024)
                min_value = min_value / (1024 * 1024 * 1024)
                unit = "GB"
            else:
                unit = metric["unit"]
            
            metric_data[metric["name"]] = {
                "average": avg_value,
                "maximum": max_value,
                "minimum": min_value,
                "unit": unit,
                "datapoints_count": len(values)
            }
    
    # 获取RDS实例详细信息
    rds = boto3.client('rds')
    instance_info = {}
    
    try:
        response = rds.describe_db_instances(DBInstanceIdentifier=RDS_INSTANCE_ID)
        if response.get('DBInstances'):
            instance = response['DBInstances'][0]
            instance_info = {
                "engine": instance.get('Engine'),
                "version": instance.get('EngineVersion'),
                "instance_class": instance.get('DBInstanceClass'),
                "status": instance.get('DBInstanceStatus'),
                "allocated_storage": instance.get('AllocatedStorage'),
                "endpoint": instance.get('Endpoint', {}).get('Address')
            }
    except Exception as e:
        print(f"Error getting RDS instance details: {e}")
    
    # 构建性能报告
    performance_report = {
        "report_type": "rds_performance",
        "timestamp": datetime.datetime.now().isoformat(),
        "period_hours": EVALUATION_PERIOD,
        "instance_id": RDS_INSTANCE_ID,
        "instance_info": instance_info,
        "metrics": metric_data,
        "anomalies": detect_anomalies(metric_data)
    }
    
    # 发送报告
    send_webhook_notification(performance_report)
    
    return {
        'statusCode': 200,
        'body': json.dumps('RDS performance report generated and sent')
    }

def detect_anomalies(metric_data):
    """检测潜在的性能问题"""
    anomalies = []
    
    # CPU使用率高
    if "CPUUtilization" in metric_data and metric_data["CPUUtilization"]["average"] > 80:
        anomalies.append({
            "metric": "CPUUtilization",
            "severity": "WARN",
            "message": f"高CPU使用率: {metric_data['CPUUtilization']['average']:.2f}%"
        })
    
    # 内存不足
    if "FreeableMemory" in metric_data and metric_data["FreeableMemory"]["average"] < 2:  # 少于2GB可用内存
        anomalies.append({
            "metric": "FreeableMemory",
            "severity": "WARN",
            "message": f"可用内存较低: {metric_data['FreeableMemory']['average']:.2f} GB"
        })
    
    # 存储空间不足
    if "FreeStorageSpace" in metric_data and metric_data["FreeStorageSpace"]["average"] < 20:  # 少于20GB可用空间
        anomalies.append({
            "metric": "FreeStorageSpace",
            "severity": "WARN",
            "message": f"可用存储空间较低: {metric_data['FreeStorageSpace']['average']:.2f} GB"
        })
    
    # 高延迟
    if "ReadLatency" in metric_data and metric_data["ReadLatency"]["average"] > 0.05:  # 读延迟大于50ms
        anomalies.append({
            "metric": "ReadLatency",
            "severity": "INFO",
            "message": f"读延迟较高: {metric_data['ReadLatency']['average']*1000:.2f} ms"
        })
    
    if "WriteLatency" in metric_data and metric_data["WriteLatency"]["average"] > 0.05:  # 写延迟大于50ms
        anomalies.append({
            "metric": "WriteLatency",
            "severity": "INFO",
            "message": f"写延迟较高: {metric_data['WriteLatency']['average']*1000:.2f} ms"
        })
    
    return anomalies

def send_webhook_notification(data):
    # 发送到Webhook
    data_bytes = json.dumps(data).encode('utf-8')
    headers = {
        'Content-Type': 'application/json'
    }
    
    req = urllib.request.Request(WEBHOOK_URL, data=data_bytes, headers=headers)
    
    try:
        with urllib.request.urlopen(req) as response:
            print(f"Notification sent, response: {response.read().decode()}")
    except Exception as e:
        print(f"Error sending notification: {e}")
```

### 案例6: CI/CD管道状态通知

```python
import json
import boto3
import urllib.request
import os
import datetime

WEBHOOK_URL = "https://your-lark-bot-domain.com/api/webhook/your-webhook-token"

def lambda_handler(event, context):
    print(f"Received event: {json.dumps(event)}")
    
    # 检查是否为CodePipeline事件
    source = event.get('source', '')
    detail_type = event.get('detail-type', '')
    
    if source == 'aws.codepipeline' and detail_type == 'CodePipeline Pipeline Execution State Change':
        return handle_pipeline_event(event)
    elif source == 'aws.codebuild' and detail_type == 'CodeBuild Build State Change':
        return handle_build_event(event)
    else:
        print(f"Unsupported event type: {source} - {detail_type}")
        return {
            'statusCode': 400,
            'body': json.dumps('Unsupported event type')
        }

def handle_pipeline_event(event):
    """处理CodePipeline状态变更事件"""
    detail = event.get('detail', {})
    
    pipeline_name = detail.get('pipeline', '')
    pipeline_execution_id = detail.get('execution-id', '')
    pipeline_state = detail.get('state', '')
    
    # 管道的状态详情
    state_details = {}
    if pipeline_state in ['FAILED', 'STOPPED']:
        # 获取更多有关失败的信息
        codepipeline = boto3.client('codepipeline')
        try:
            execution_details = codepipeline.get_pipeline_execution(
                pipelineName=pipeline_name,
                pipelineExecutionId=pipeline_execution_id
            )
            
            # 提取阶段状态信息
            stages = []
            pipeline_execution = execution_details.get('pipelineExecution', {})
            
            # 获取当前管道的配置
            pipeline_response = codepipeline.get_pipeline(name=pipeline_name)
            pipeline_config = pipeline_response.get('pipeline', {})
            
            # 获取各阶段状态
            for stage_config in pipeline_config.get('stages', []):
                stage_name = stage_config.get('name', '')
                
                # 获取此执行中的阶段状态
                stage_states_response = codepipeline.get_pipeline_state(name=pipeline_name)
                for stage_state in stage_states_response.get('stageStates', []):
                    if stage_state.get('stageName') == stage_name:
                        stage_status = {
                            'name': stage_name,
                            'status': stage_state.get('latestExecution', {}).get('status', 'UNKNOWN'),
                            'actions': []
                        }
                        
                        # 添加动作信息
                        for action_state in stage_state.get('actionStates', []):
                            action_name = action_state.get('actionName', '')
                            action_status = {
                                'name': action_name,
                                'status': 'UNKNOWN'
                            }
                            
                            # 添加错误信息
                            latest_execution = action_state.get('latestExecution', {})
                            if latest_execution:
                                action_status['status'] = latest_execution.get('status', 'UNKNOWN')
                                
                                if latest_execution.get('status') == 'FAILED':
                                    error_details = latest_execution.get('errorDetails', {})
                                    if error_details:
                                        action_status['error_message'] = error_details.get('message', '')
                                        action_status['error_code'] = error_details.get('code', '')
                            
                            stage_status['actions'].append(action_status)
                        
                        stages.append(stage_status)
                        break
            
            state_details = {
                'stages': stages,
                'revision': pipeline_execution.get('artifactRevisions', [])
            }
        except Exception as e:
            print(f"Error getting pipeline details: {e}")
            state_details = {'error': str(e)}
    
    # 构造管道状态报告
    pipeline_info = {
        'event_type': 'cicd_status',
        'source': 'codepipeline',
        'pipeline_name': pipeline_name,
        'execution_id': pipeline_execution_id,
        'state': pipeline_state,
        'state_details': state_details,
        'region': event.get('region', ''),
        'account': event.get('account', ''),
        'timestamp': datetime.datetime.now().isoformat(),
        'event_time': event.get('time', ''),
    }
    
    # 获取提交信息
    try:
        commit_info = get_commit_info(detail)
        if commit_info:
            pipeline_info['commit_info'] = commit_info
    except Exception as e:
        print(f"Error getting commit info: {e}")
    
    # 发送通知
    send_webhook_notification(pipeline_info)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Pipeline event processed successfully')
    }

def handle_build_event(event):
    """处理CodeBuild构建状态变更事件"""
    detail = event.get('detail', {})
    
    build_id = detail.get('build-id', '')
    build_status = detail.get('build-status', '')
    project_name = detail.get('project-name', '')
    
    # 创建CodeBuild客户端
    codebuild = boto3.client('codebuild')
    
    build_details = {}
    try:
        response = codebuild.batch_get_builds(ids=[build_id])
        if response.get('builds'):
            build = response['builds'][0]
            
            # 提取详细信息
            build_details = {
                'project_name': build.get('projectName', ''),
                'start_time': build.get('startTime', '').isoformat() if build.get('startTime') else None,
                'end_time': build.get('endTime', '').isoformat() if build.get('endTime') else None,
                'duration': (build.get('endTime') - build.get('startTime')).total_seconds() if build.get('endTime') and build.get('startTime') else None,
                'initiator': build.get('initiator', ''),
                'source_version': build.get('sourceVersion', ''),
                'source_type': build.get('source', {}).get('type', ''),
                'logs': {
                    'group': build.get('logs', {}).get('groupName', ''),
                    'stream': build.get('logs', {}).get('streamName', ''),
                    'url': build.get('logs', {}).get('deepLink', '')
                }
            }
            
            # 如果构建失败，获取失败信息
            if build_status == 'FAILED':
                build_details['phases'] = []
                for phase in build.get('phases', []):
                    phase_info = {
                        'name': phase.get('phaseType', ''),
                        'status': phase.get('phaseStatus', ''),
                        'duration': phase.get('durationInSeconds', 0)
                    }
                    
                    # 添加错误信息
                    if phase.get('phaseStatus') == 'FAILED' and 'contexts' in phase:
                        error_contexts = []
                        for context in phase.get('contexts', []):
                            error_contexts.append({
                                'status_code': context.get('statusCode', ''),
                                'message': context.get('message', '')
                            })
                        phase_info['errors'] = error_contexts
                    
                    build_details['phases'].append(phase_info)
    except Exception as e:
        print(f"Error getting build details: {e}")
        build_details = {'error': str(e)}
    
    # 构造构建状态报告
    build_info = {
        'event_type': 'cicd_status',
        'source': 'codebuild',
        'build_id': build_id,
        'project_name': project_name,
        'status': build_status,
        'build_details': build_details,
        'region': event.get('region', ''),
        'account': event.get('account', ''),
        'timestamp': datetime.datetime.now().isoformat(),
        'event_time': event.get('time', '')
    }
    
    # 发送通知
    send_webhook_notification(build_info)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Build event processed successfully')
    }

def get_commit_info(detail):
    """尝试获取提交信息"""
    try:
        # 从管道执行中获取提交信息
        codepipeline = boto3.client('codepipeline')
        pipeline_name = detail.get('pipeline', '')
        execution_id = detail.get('execution-id', '')
        
        execution_details = codepipeline.get_pipeline_execution(
            pipelineName=pipeline_name,
            pipelineExecutionId=execution_id
        )
        
        artifact_revisions = execution_details.get('pipelineExecution', {}).get('artifactRevisions', [])
        if not artifact_revisions:
            return None
        
        # 获取提交信息
        for revision in artifact_revisions:
            if revision.get('revisionType') == 'GitHub' or revision.get('revisionType') == 'CodeCommit':
                return {
                    'repository': revision.get('name', ''),
                    'commit_id': revision.get('revisionId', ''),
                    'commit_message': revision.get('revisionSummary', ''),
                    'commit_url': revision.get('revisionUrl', '')
                }
        
        return None
    except Exception as e:
        print(f"Error in get_commit_info: {e}")
        return None

def send_webhook_notification(data):
    # 发送到Webhook
    data_bytes = json.dumps(data).encode('utf-8')
    headers = {
        'Content-Type': 'application/json'
    }
    
    req = urllib.request.Request(WEBHOOK_URL, data=data_bytes, headers=headers)
    
    try:
        with urllib.request.urlopen(req) as response:
            print(f"Notification sent, response: {response.read().decode()}")
    except Exception as e:
        print(f"Error sending notification: {e}")
```

## 总结

这些案例展示了如何将飞书的Webhook功能与AWS Lambda和各种AWS服务集成，以实现自动化监控和智能通知：

1. **费用异常监控**: 通过定期检查AWS Cost Explorer数据，发现并分析费用异常情况
2. **CloudWatch告警监控**: 实时监控CloudWatch告警，并提供上下文和建议
3. **CloudEvents事件处理**: 处理符合CloudEvents标准的云事件，并智能分类和提供安全建议
4. **服务健康状态汇总**: 定期收集和汇总AWS服务健康状态，提供整体视图
5. **数据库性能监控**: 分析RDS数据库性能指标，主动发现潜在问题
6. **CI/CD管道状态通知**: 实时通知CI/CD流程状态，包括详细的失败原因分析

通过将这些Lambda函数与飞书Webhook结合，您可以实现：

- 智能异常分析：利用AI模型分析复杂的告警和事件数据
- 自动上下文关联：将相关的系统状态信息关联到通知中
- 主动建议：提供针对性的解决方案建议
- 结构化展现：通过Markdown格式美化消息呈现

这些案例可以根据您的具体需求进行调整和扩展，实现更全面的云资源监控和运维自动化。
