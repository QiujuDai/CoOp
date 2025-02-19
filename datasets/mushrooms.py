import os
import pickle
import math
import random
from collections import defaultdict

from dassl.data.datasets import DATASET_REGISTRY, Datum, DatasetBase
from dassl.utils import read_json, write_json, mkdir_if_missing


@DATASET_REGISTRY.register()
class Mushrooms(DatasetBase):

    dataset_dir = "mushrooms_dataset"

    def __init__(self, cfg):
        root = os.path.abspath(os.path.expanduser(cfg.DATASET.ROOT))
        
        self.dataset_dir = os.path.join(root, self.dataset_dir)
        self.split_path = os.path.join(self.dataset_dir, "split_mushrooms.json")
        self.img_dir = os.path.join(self.dataset_dir, "data")

        if os.path.exists(self.split_path):
            train, val, test = self.read_split(self.split_path, self.img_dir)
        else:
            trainval = self.read_data(split_file="trainval.txt", img_dir=self.img_dir)
            test = self.read_data(split_file="test.txt", img_dir=self.img_dir)
            train, val = self.split_trainval(trainval)
            self.save_split(train, val, test, self.split_path)

        num_shots = cfg.DATASET.NUM_SHOTS
        if num_shots >= 1:
            seed = cfg.SEED
            preprocessed = os.path.join(self.dataset_dir, f"shot_{num_shots}-seed_{seed}.pkl")
            
            if os.path.exists(preprocessed):
                print(f"Loading preprocessed few-shot data from {preprocessed}")
                with open(preprocessed, "rb") as file:
                    data = pickle.load(file)
                    train, val = data["train"], data["val"]
            else:
                # for item in val:
                #     print(f"444 impath:{item.impath}")

                train = self.generate_fewshot_dataset(train, num_shots=num_shots)
                val = self.generate_fewshot_dataset(val, num_shots=min(num_shots, 4))

                # for item in val:
                #     print(f"555 impath:{item.impath}")

                data = {"train": train, "val": val}
                print(f"Saving preprocessed few-shot data to {preprocessed}")
                with open(preprocessed, "wb") as file:
                    pickle.dump(data, file, protocol=pickle.HIGHEST_PROTOCOL)

        subsample = cfg.DATASET.SUBSAMPLE_CLASSES
        # print(f"subsample:{subsample}")

        # for item in train:
        #     print(f"666 impath:{item.impath}")
        # for item in val:
        #     print(f"777 impath:{item.impath}")
        # for item in test:
        #     print(f"888 impath:{item.impath}")
        train, val, test = self.subsample_classes(train, val, test, subsample=subsample)

        super().__init__(train_x=train, val=val, test=test)

    def read_data(self, split_file, img_dir):
        filepath = os.path.join(self.dataset_dir, split_file)
        items = []

        with open(filepath, "r") as f:
            lines = f.readlines()
            for line in lines:
                line = line.strip()
                impath, label, classname = line.split(" ")
                impath = os.path.join(img_dir, impath)
                label = int(label)  # convert to 0-based index
                item = Datum(impath=impath, label=label, classname=classname)
                items.append(item)

        return items

    @staticmethod
    def split_trainval(trainval, p_val=0.2):
        p_trn = 1 - p_val
        print(f"Splitting trainval into {p_trn:.0%} train and {p_val:.0%} val")
        tracker = defaultdict(list)
        for idx, item in enumerate(trainval):
            label = item.label
            tracker[label].append(idx)

        train, val = [], []
        for label, idxs in tracker.items():
            n_val = round(len(idxs) * p_val)
            assert n_val > 0
            random.shuffle(idxs)
            for n, idx in enumerate(idxs):
                item = trainval[idx]
                if n < n_val:
                    val.append(item)
                else:
                    train.append(item)

        return train, val

    @staticmethod
    def save_split(train, val, test, filepath):
        def _extract(items):
            out = []
            for item in items:
                impath = item.impath
                impath = impath.split("data/")[-1]
                # print(impath)
                label = item.label
                classname = item.classname
                out.append((impath, label, classname))
            return out

        train = _extract(train)
        val = _extract(val)
        test = _extract(test)

        split = {"train": train, "val": val, "test": test}

        write_json(split, filepath)
        print(f"Saved split to {filepath}")

    @staticmethod
    def read_split(filepath, img_dir):
        def _convert(items):
            out = []
            for impath, label, classname in items:
                # print(f"111 impath:{impath}, img_dir:{img_dir}")
                impath2 = os.path.join(img_dir, impath)
                # print(f"222 impath:{impath2}, img_dir:{img_dir}")
                
                item = Datum(impath=impath2, label=int(label), classname=classname)
                out.append(item)
            return out

        print(f"Reading split from {filepath}")
        split = read_json(filepath)
        train = _convert(split["train"])
        val = _convert(split["val"])
        test = _convert(split["test"])

        return train, val, test
    
    @staticmethod
    def subsample_classes(*args, subsample="all"):
        """Divide classes into two groups. The first group
        represents base classes while the second group represents
        new classes.

        Args:
            args: a list of datasets, e.g. train, val and test.
            subsample (str): what classes to subsample.
        """
        assert subsample in ["all", "base", "new"]

        if subsample == "all":
            return args
        
        dataset = args[0]
        labels = set()
        for item in dataset:
            labels.add(item.label)
        labels = list(labels)
        labels.sort()
        n = len(labels)
        # Divide classes into two halves
        m = math.ceil(n / 2)

        print(f"SUBSAMPLE {subsample.upper()} CLASSES!")
        if subsample == "base":
            selected = labels[:m]  # take the first half
        else:
            selected = labels[m:]  # take the second half
        relabeler = {y: y_new for y_new, y in enumerate(selected)}
        
        output = []
        for dataset in args:
            dataset_new = []
            for item in dataset:
                if item.label not in selected:
                    continue
                # print(f"item impath: {item.impath}")
                item_new = Datum(
                    impath=item.impath,
                    label=relabeler[item.label],
                    classname=item.classname
                )
                dataset_new.append(item_new)
            output.append(dataset_new)
        
        return output
