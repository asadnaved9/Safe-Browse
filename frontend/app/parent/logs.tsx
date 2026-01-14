import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../contexts/AuthContext';
import axios from 'axios';
import Constants from 'expo-constants';
import { format } from 'date-fns';

const API_URL = Constants.expoConfig?.extra?.EXPO_PUBLIC_BACKEND_URL || process.env.EXPO_PUBLIC_BACKEND_URL;

interface Log {
  id: string;
  profile_id: string;
  profile_name: string;
  content_type: string;
  detected_at: string;
  is_safe: boolean;
  confidence: number;
  reasons: string[];
  content_snippet: string;
  url?: string;
}

export default function Logs() {
  const { token } = useAuth();
  const [logs, setLogs] = useState<Log[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadLogs();
  }, []);

  const loadLogs = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/logs?limit=50`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setLogs(response.data);
    } catch (error) {
      console.error('Error loading logs:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      loadLogs();
      return;
    }

    try {
      const response = await axios.get(
        `${API_URL}/api/logs/search?keyword=${encodeURIComponent(searchQuery)}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      setLogs(response.data);
    } catch (error) {
      console.error('Error searching logs:', error);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    loadLogs();
  };

  const getContentTypeIcon = (type: string) => {
    switch (type) {
      case 'text':
        return 'text';
      case 'image':
        return 'image';
      case 'url':
        return 'globe';
      default:
        return 'alert-circle';
    }
  };

  const filteredLogs = logs.filter((log) => !log.is_safe);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Activity Logs</Text>
      </View>

      <View style={styles.searchContainer}>
        <Ionicons name="search" size={20} color="#64748b" style={styles.searchIcon} />
        <TextInput
          style={styles.searchInput}
          placeholder="Search logs..."
          placeholderTextColor="#64748b"
          value={searchQuery}
          onChangeText={setSearchQuery}
          onSubmitEditing={handleSearch}
        />
        {searchQuery.length > 0 && (
          <TouchableOpacity
            onPress={() => {
              setSearchQuery('');
              loadLogs();
            }}
          >
            <Ionicons name="close-circle" size={20} color="#64748b" />
          </TouchableOpacity>
        )}
      </View>

      <ScrollView
        style={styles.scrollView}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
      >
        {filteredLogs.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="checkmark-circle" size={64} color="#10b981" />
            <Text style={styles.emptyText}>No harmful content detected</Text>
            <Text style={styles.emptySubtext}>Your children are browsing safely</Text>
          </View>
        ) : (
          filteredLogs.map((log) => (
            <View key={log.id} style={styles.logCard}>
              <View style={styles.logHeader}>
                <View style={styles.logIconContainer}>
                  <Ionicons
                    name={getContentTypeIcon(log.content_type)}
                    size={20}
                    color="#ef4444"
                  />
                </View>
                <View style={styles.logHeaderInfo}>
                  <Text style={styles.logProfile}>{log.profile_name}</Text>
                  <Text style={styles.logTime}>
                    {format(new Date(log.detected_at), 'MMM d, h:mm a')}
                  </Text>
                </View>
                <View style={styles.confidenceBadge}>
                  <Text style={styles.confidenceText}>
                    {Math.round(log.confidence * 100)}%
                  </Text>
                </View>
              </View>

              <View style={styles.logContent}>
                {log.reasons.map((reason, index) => (
                  <View key={index} style={styles.reasonTag}>
                    <Ionicons name="warning" size={12} color="#ef4444" />
                    <Text style={styles.reasonText}>{reason}</Text>
                  </View>
                ))}

                {log.content_snippet && (
                  <View style={styles.snippetContainer}>
                    <Text style={styles.snippetLabel}>Content:</Text>
                    <Text style={styles.snippetText} numberOfLines={3}>
                      {log.content_snippet}
                    </Text>
                  </View>
                )}

                {log.url && (
                  <View style={styles.urlContainer}>
                    <Ionicons name="link" size={12} color="#64748b" />
                    <Text style={styles.urlText} numberOfLines={1}>
                      {log.url}
                    </Text>
                  </View>
                )}
              </View>
            </View>
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f172a',
  },
  header: {
    padding: 24,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#f1f5f9',
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1e293b',
    borderRadius: 12,
    marginHorizontal: 24,
    marginBottom: 16,
    paddingHorizontal: 16,
    borderWidth: 1,
    borderColor: '#334155',
  },
  searchIcon: {
    marginRight: 12,
  },
  searchInput: {
    flex: 1,
    height: 48,
    color: '#f1f5f9',
    fontSize: 16,
  },
  scrollView: {
    flex: 1,
    padding: 24,
    paddingTop: 0,
  },
  emptyState: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingTop: 80,
  },
  emptyText: {
    fontSize: 18,
    color: '#94a3b8',
    marginTop: 16,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#64748b',
    marginTop: 8,
  },
  logCard: {
    backgroundColor: '#1e293b',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#334155',
  },
  logHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  logIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#ef444420',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  logHeaderInfo: {
    flex: 1,
  },
  logProfile: {
    fontSize: 16,
    fontWeight: '600',
    color: '#f1f5f9',
  },
  logTime: {
    fontSize: 12,
    color: '#64748b',
    marginTop: 2,
  },
  confidenceBadge: {
    backgroundColor: '#ef444420',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 12,
  },
  confidenceText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#ef4444',
  },
  logContent: {
    marginTop: 8,
  },
  reasonTag: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ef444410',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    marginRight: 8,
    marginBottom: 8,
    alignSelf: 'flex-start',
  },
  reasonText: {
    fontSize: 12,
    color: '#ef4444',
    marginLeft: 4,
  },
  snippetContainer: {
    marginTop: 8,
  },
  snippetLabel: {
    fontSize: 12,
    color: '#64748b',
    marginBottom: 4,
  },
  snippetText: {
    fontSize: 14,
    color: '#94a3b8',
    lineHeight: 20,
  },
  urlContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 8,
  },
  urlText: {
    fontSize: 12,
    color: '#64748b',
    marginLeft: 4,
    flex: 1,
  },
});
