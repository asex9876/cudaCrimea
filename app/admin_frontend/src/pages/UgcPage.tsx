import {
  Heading,
  Text,
  Stack,
  Box,
  Button,
  HStack,
  Spinner,
  Alert,
  AlertIcon,
  SimpleGrid,
  Image,
  VStack,
  Code,
  Divider,
  useDisclosure,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalCloseButton,
  ModalBody,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import { fetchUGCList, fetchUGCItem } from "../api/ugc";
import type { UGCItem } from "../api/types";
import { useState } from "react";

const UgcPreviewModal = ({ item, onClose }: { item: UGCItem | null; onClose: () => void }) => (
  <Modal isOpen={Boolean(item)} onClose={onClose} size="xl" scrollBehavior="inside">
    <ModalOverlay />
    <ModalContent bg="gray.900">
      <ModalHeader>Черновик заявки</ModalHeader>
      <ModalCloseButton />
      <ModalBody pb={6}>
        {item ? (
          <Stack spacing={4}>
            <Text fontWeight="semibold">{item.preview.title ?? "Без названия"}</Text>
            <Code whiteSpace="pre-wrap">{JSON.stringify(item.payload, null, 2)}</Code>
            <Text fontFamily="mono" whiteSpace="pre-wrap">
              {item.caption}
            </Text>
          </Stack>
        ) : null}
      </ModalBody>
    </ModalContent>
  </Modal>
);

const UgcCard = ({ item, onInspect }: { item: UGCItem; onInspect: (id: string) => void }) => (
  <Box bg="gray.800" borderWidth="1px" borderColor="whiteAlpha.200" rounded="lg" p={4}>
    <HStack justify="space-between" align="flex-start">
      <Stack spacing={1}>
        <Text fontWeight="semibold">{item.preview.title ?? "Без названия"}</Text>
        <Text fontSize="sm" color="gray.400">
          {item.preview.date_iso || "Дата не указана"}
          {item.preview.time_24h ? ` · ${item.preview.time_24h}` : ""}
        </Text>
        <Text fontSize="sm" color="gray.400">
          {item.preview.venue_name || item.preview.address || "Место не указано"}
        </Text>
      </Stack>
      <Button size="sm" variant="outline" onClick={() => onInspect(item.id)}>
        Смотреть сырой JSON
      </Button>
    </HStack>

    <Text mt={3} fontSize="sm" color="gray.300" whiteSpace="pre-wrap">
      {item.caption}
    </Text>

    {item.images.length ? (
      <SimpleGrid columns={{ base: 2, md: 3 }} spacing={2} mt={3}>
        {item.images.slice(0, 6).map((img) => (
          <Image
            key={img}
            src={img.startsWith("http") ? img : undefined}
            alt={item.preview.title ?? "cover"}
            borderRadius="md"
            borderWidth="1px"
            borderColor="whiteAlpha.200"
            fallback={<Box bg="gray.700" h="80px" borderRadius="md" />}
            h="80px"
            objectFit="cover"
          />
        ))}
      </SimpleGrid>
    ) : null}

    <Divider my={3} borderColor="whiteAlpha.200" />

    <HStack spacing={3}>
      <Button size="sm" colorScheme="purple" variant="solid" isDisabled>
        Одобрить (скоро)
      </Button>
      <Button size="sm" variant="outline" colorScheme="red" isDisabled>
        Отклонить
      </Button>
    </HStack>
  </Box>
);

const UgcPage = () => {
  const [inspectId, setInspectId] = useState<string | null>(null);
  const {
    data,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["ugc-list"],
    queryFn: () => fetchUGCList({ limit: 20, offset: 0 }),
    staleTime: 30_000,
  });

  const {
    data: inspected,
  } = useQuery({
    queryKey: ["ugc-item", inspectId],
    queryFn: () => fetchUGCItem(inspectId!),
    enabled: Boolean(inspectId),
  });

  return (
    <Stack spacing={4}>
      <HStack justify="space-between" align="center">
        <Heading size="lg">UGC очередь</Heading>
        <Button size="sm" variant="outline" onClick={() => refetch()}>
          Обновить
        </Button>
      </HStack>

      {isLoading ? (
        <HStack spacing={3}>
          <Spinner size="sm" />
          <Text color="gray.400">Загружаем заявки…</Text>
        </HStack>
      ) : null}
      {isError ? (
        <Alert status="error" borderRadius="md" variant="subtle">
          <AlertIcon />
          Не удалось получить список заявок.
        </Alert>
      ) : null}

      {data && data.total === 0 ? (
        <Text color="gray.500">Очередь пуста — пользователи пока ничего не прислали.</Text>
      ) : null}

      <VStack align="stretch" spacing={4}>
        {data?.items.map((item) => (
          <UgcCard key={item.id} item={item} onInspect={(id) => setInspectId(id)} />
        ))}
      </VStack>

      <UgcPreviewModal item={inspected ?? null} onClose={() => setInspectId(null)} />
    </Stack>
  );
};

export default UgcPage;
