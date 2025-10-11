import {
  SimpleGrid,
  Heading,
  Stack,
  Text,
  Box,
  HStack,
  Button,
  Spinner,
  Alert,
  AlertIcon,
  VStack,
  Badge,
  Divider,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import StatCard from "../components/StatCard";
import { fetchDashboardSummary } from "../api/dashboard";

const DashboardPage = () => {
  const {
    data,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: fetchDashboardSummary,
    staleTime: 60_000,
  });

  return (
    <Stack spacing={6}>
      <HStack justify="space-between" align="center">
        <Heading size="lg">Дашборд</Heading>
        <Button size="sm" variant="outline" onClick={() => refetch()}>
          Обновить
        </Button>
      </HStack>

      {isLoading ? (
        <HStack spacing={3}>
          <Spinner size="sm" />
          <Text color="gray.400">Загружаем данные…</Text>
        </HStack>
      ) : null}
      {isError ? (
        <Alert status="error" borderRadius="md" variant="subtle">
          <AlertIcon />
          Не удалось получить данные дашборда.
        </Alert>
      ) : null}

      <SimpleGrid columns={{ base: 1, md: 2, xl: 4 }} spacing={4}>
        <StatCard label="Новые заявки" value={data?.new_requests ?? "—"} />
        <StatCard label="Опубликовано сегодня" value={data?.published_today ?? "—"} />
        <StatCard
          label="CTR за 7 дней"
          value={data ? `${(data.ctr_week * 100).toFixed(1)} %` : "—"}
        />
        <StatCard label="Ошибки интеграций" value={data?.error_count ?? "—"} />
      </SimpleGrid>

      <Box
        bg="gray.800"
        borderWidth="1px"
        borderColor="whiteAlpha.200"
        rounded="lg"
        p={5}
      >
        <Heading size="md" mb={4}>
          Очередь задач
        </Heading>
        {data && data.tasks.length > 0 ? (
          <VStack align="stretch" spacing={3}>
            {data.tasks.map((task) => (
              <Box key={task.id} p={3} bg="gray.900" borderRadius="md" borderWidth="1px" borderColor="whiteAlpha.100">
                <HStack justify="space-between" align="flex-start">
                  <Box>
                    <Text fontWeight="semibold">{task.title ?? "Без названия"}</Text>
                    <Text fontSize="sm" color="gray.400">
                      {task.submitted_at ? new Date(task.submitted_at).toLocaleString() : "Время не указано"}
                    </Text>
                  </Box>
                  <Badge colorScheme="purple" variant="outline">
                    {task.status}
                  </Badge>
                </HStack>
              </Box>
            ))}
          </VStack>
        ) : (
          <Text color="gray.500">Очередь задач пуста — отличный момент, чтобы отдохнуть.</Text>
        )}
      </Box>

      <Divider borderColor="whiteAlpha.200" />

      <Text fontSize="sm" color="gray.500">
        Данные обновляются каждые 60 секунд. Интерактивные графики и расширенные отчёты добавим в следующей итерации.
      </Text>
    </Stack>
  );
};

export default DashboardPage;
